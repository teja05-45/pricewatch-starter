"""Scout agent: finds product URLs on a store's index page.

Returns absolute URLs. If the index can't be read (challenge page, rate limit, robot check),
returns an empty list and a note; the orchestrator records the note.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import Client

PRODUCT_PATH = {
    "corner": r"/stores/corner/p/[^/?#]+$",
    "maple": r"/stores/maple/products/[^/?#]+$",
    "zon": r"/stores/zon/dp/[^/?#]+$",
    "shield": r"/stores/shield/item/[^/?#]+$",
    "flux": r"/stores/flux/item/[^/?#]+$",
}


def discover(client: Client, store: str, index_url: str) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    r = client.get(index_url)
    if r.status_code != 200:
        notes.append(f"index returned HTTP {r.status_code}")
        return [], notes
    if "Are you a human" in r.text:
        notes.append("index served a robot check")
        return [], notes
    soup = BeautifulSoup(r.text, "html.parser")
    pat = re.compile(PRODUCT_PATH.get(store, r".*"))
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(index_url, a["href"])
        if pat.search(href) and href not in urls:
            urls.append(href)
    return urls, notes
