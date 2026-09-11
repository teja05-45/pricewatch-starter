import hashlib
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 PriceWatch/0.1",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class Client:
    def __init__(self, min_interval: float = 0.0, timeout: float = 10.0, retries: int = 4):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=32)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.min_interval = min_interval  # seconds between requests to the same host
        self.timeout = timeout
        self.retries = retries
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._challenge_lock = threading.Lock()

    def _get_host_lock(self, host: str) -> threading.Lock:
        with self._lock:
            if host not in self._host_locks:
                self._host_locks[host] = threading.Lock()
            return self._host_locks[host]

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0)
            wait = max(last - now, last + self.min_interval - now)
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._last[host] = now

    def _set_backoff(self, url: str, delay: float) -> None:
        host = urlparse(url).netloc
        with self._lock:
            target = time.monotonic() + delay
            if target > self._last.get(host, 0):
                self._last[host] = target

    def _parse_retry_after(self, val: str | None) -> float | None:
        if not val:
            return None
        v = val.strip().strip('"')
        try:
            return max(0.0, float(v))
        except ValueError:
            pass
        try:
            from datetime import datetime, timezone
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(v)
            if dt:
                now = datetime.now(timezone.utc)
                return max(0.0, (dt - now).total_seconds())
        except Exception:
            pass
        return None

    def _solve_shield_challenge(self, r: requests.Response) -> bool:
        """Solves Shield 503 challenge: SHA-256(s + '|' + p)[:16]."""
        if "cf-c" not in r.text:
            return False

        with self._challenge_lock:
            soup = BeautifulSoup(r.text, "html.parser")
            cf_el = soup.find(id="cf-c")
            if not cf_el or not cf_el.get("data-s") or not cf_el.get("data-p"):
                return False

            s = str(cf_el["data-s"])
            p = str(cf_el["data-p"])

            # s = data-s, p = data-p
            # SHA-256(s + "|" + p)[:16]
            raw_str = f"{s}|{p}"
            answer = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]

            retry_sec = self._parse_retry_after(r.headers.get("Retry-After"))
            delay = retry_sec if retry_sec is not None else 1.35
            self._set_backoff(r.url, delay)

            challenge_url = urljoin(r.url, "/stores/shield/challenge")
            payload = {"s": s, "p": p, "a": answer}

            for post_attempt in range(3):
                self._throttle(challenge_url)
                try:
                    res = self.session.post(
                        challenge_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=self.timeout,
                    )
                    if res.status_code == 200:
                        return True
                    if res.status_code in (429, 503) and post_attempt < 2:
                        post_retry = self._parse_retry_after(res.headers.get("Retry-After"))
                        post_delay = post_retry if post_retry is not None else (1.0 * (post_attempt + 1))
                        self._set_backoff(challenge_url, post_delay)
                        continue
                    return False
                except requests.RequestException:
                    if post_attempt < 2:
                        self._set_backoff(challenge_url, 1.0 * (post_attempt + 1))
                        continue
                    return False
            return False

    def request(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", self.timeout)
        host = urlparse(url).netloc
        host_lock = self._get_host_lock(host)

        with host_lock:
            last_exc: Exception | None = None
            for attempt in range(self.retries + 1):
                self._throttle(url)
                try:
                    r = self.session.request(method, url, **kw)
                except requests.RequestException as e:  # network blip
                    last_exc = e
                    self._set_backoff(url, 0.5 * (attempt + 1))
                    continue

                # Shield challenge detection & resolution
                if (r.status_code == 503 or "cf-c" in r.text) and attempt < self.retries:
                    if self._solve_shield_challenge(r):
                        continue

                if r.status_code in (429, 503):
                    if attempt < self.retries:
                        retry_sec = self._parse_retry_after(r.headers.get("Retry-After"))
                        delay = retry_sec if retry_sec is not None else (0.5 * (attempt + 1))
                        self._set_backoff(url, delay)
                        continue
                return r
            if last_exc:
                raise last_exc
            return r  # type: ignore[possibly-undefined]

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)

