import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from pricewatch.agents.extractor import extract_shield
from pricewatch.http import Client


def test_shield_test_a_challenge_parsing():
    """Test A: Challenge SHA256 answer calculation given data-s and data-p."""
    s = "abc123"
    p = "/stores/shield/item/test"
    answer = hashlib.sha256(f"{s}|{p}".encode("utf-8")).hexdigest()[:16]
    assert len(answer) == 16
    assert answer == hashlib.sha256(b"abc123|/stores/shield/item/test").hexdigest()[:16]


def test_shield_test_b_challenge_post_same_session():
    """Test B: Verify GET product -> 503 challenge -> POST /stores/shield/challenge -> 200 -> GET product -> 200 actual HTML all use the SAME session."""
    client = Client()

    resp_503 = MagicMock(spec=requests.Response)
    resp_503.status_code = 503
    resp_503.text = '<div id="cf-c" data-s="s_val_1" data-p="/stores/shield/item/prod_b">Challenge</div>'
    resp_503.url = "http://localhost:4000/stores/shield/item/prod_b"
    resp_503.headers = {"Retry-After": "0"}

    resp_post_200 = MagicMock(spec=requests.Response)
    resp_post_200.status_code = 200
    resp_post_200.text = '{"ok": true}'

    resp_get_200 = MagicMock(spec=requests.Response)
    resp_get_200.status_code = 200
    resp_get_200.text = '<html><body><script>window.__STATE__={"product":{"id":"prod_b","title":"Test Item B","offer":{"amount":4500,"currency":"GBP","was":null,"stock":"IN_STOCK"}}};</script></body></html>'

    posted_sessions = []

    def fake_post(url, **kwargs):
        posted_sessions.append(client.session)
        client.session.cookies.set("shield_clearance", "clear_val_99")
        return resp_post_200

    def fake_request(method, url, **kwargs):
        if method == "GET" and "shield_clearance" not in client.session.cookies:
            return resp_503
        return resp_get_200

    with patch.object(client.session, "request", side_effect=fake_request), \
         patch.object(client.session, "post", side_effect=fake_post) as mock_post, \
         patch("time.sleep"):
        r = client.get("http://localhost:4000/stores/shield/item/prod_b")
        assert r.status_code == 200
        assert "window.__STATE__" in r.text
        assert len(posted_sessions) == 1
        assert posted_sessions[0] is client.session
        assert client.session.cookies.get("shield_clearance") == "clear_val_99"


def test_shield_test_c_final_extraction():
    """Test C: Post-challenge actual HTML parsing verifies name, price_cents, currency, availability, and no pending note."""
    html = """
    <html>
      <body>
        <script>
          window.__STATE__={"product":{"id":"prod_c","title":"Shield Waterproof Boots","offer":{"amount":12500,"currency":"GBP","was":15000,"stock":"IN_STOCK"}}};
        </script>
      </body>
    </html>
    """
    mock_client = MagicMock(spec=Client)
    obs = extract_shield(mock_client, "shield", "http://localhost:4000/stores/shield/item/prod_c", html)

    assert obs.name == "Shield Waterproof Boots"
    assert obs.price_cents == 12500
    assert obs.currency == "GBP"
    assert obs.compare_at_cents == 15000
    assert obs.availability == "in_stock"
    assert "shield extraction pending" not in obs.notes
    assert obs.notes == []


def test_shield_test_d_retry_after():
    """Test D: 503/429 response with Retry-After header respects delay without uncontrolled infinite loop."""
    client = Client(retries=2)

    resp_429 = MagicMock(spec=requests.Response)
    resp_429.status_code = 429
    resp_429.text = "Too Many Requests"
    resp_429.headers = {"Retry-After": "2"}

    resp_200 = MagicMock(spec=requests.Response)
    resp_200.status_code = 200
    resp_200.text = "OK"

    sleep_calls = []

    def fake_sleep(duration):
        sleep_calls.append(duration)

    with patch.object(client.session, "request", side_effect=[resp_429, resp_200]), \
         patch("time.sleep", side_effect=fake_sleep):
        r = client.get("http://localhost:4000/stores/shield/item/retry_test")
        assert r.status_code == 200
        assert any(abs(x - 2.0) < 0.01 for x in sleep_calls)



def test_shield_challenge_solver_and_cookie_persistence():
    client = Client()

    challenge_html = """
    <html>
      <body>
        <div id="cf-c" data-s="token_dyn_77" data-p="/stores/shield/item/PROD-1">Checking your browser...</div>
      </body>
    </html>
    """

    mock_r = MagicMock(spec=requests.Response)
    mock_r.text = challenge_html
    mock_r.url = "http://localhost:4000/stores/shield/item/PROD-1"
    mock_r.headers = {"Retry-After": "0"}

    mock_post_resp = MagicMock(spec=requests.Response)
    mock_post_resp.status_code = 200

    def fake_post(url, json=None, **kwargs):
        client.session.cookies.set("shield_clearance", "cookie_val_123")
        return mock_post_resp

    with patch.object(client.session, "post", side_effect=fake_post) as mock_post, patch("time.sleep"):
        success = client._solve_shield_challenge(mock_r)
        assert success is True

        mock_post.assert_called_once()
        call_url, call_kwargs = mock_post.call_args
        assert call_url[0] == "http://localhost:4000/stores/shield/challenge"
        payload = call_kwargs["json"]
        assert payload["s"] == "token_dyn_77"
        assert payload["p"] == "/stores/shield/item/PROD-1"

        expected_a = hashlib.sha256(b"token_dyn_77|/stores/shield/item/PROD-1").hexdigest()[:16]
        assert payload["a"] == expected_a

        assert client.session.cookies.get("shield_clearance") == "cookie_val_123"


def test_shield_window_state_product_extraction():
    html = """
    <!doctype html>
    <html>
      <head><title>Aurel Solstice Mechanical Keyboard — Shield Outfitters</title></head>
      <body>
        <h1 id="title">Loading…</h1>
        <strong id="price">Loading…</strong>
        <script>
          window.__STATE__={"product":{"id":"SH-CUSTOM-1","title":"Aurel Solstice Mechanical Keyboard","offer":{"amount":88574,"currency":"GBP","was":134855,"stock":"IN_STOCK"}}};
        </script>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)
    obs = extract_shield(mock_client, "shield", "http://localhost:4000/stores/shield/item/SH-CUSTOM-1", html)

    assert obs.store == "shield"
    assert obs.product_id == "SH-CUSTOM-1"
    assert obs.name == "Aurel Solstice Mechanical Keyboard"
    assert obs.price_cents == 88574
    assert obs.currency == "GBP"
    assert obs.compare_at_cents == 134855
    assert obs.availability == "in_stock"
    assert obs.source == "rules"
    assert obs.notes == []


def test_shield_window_state_out_of_stock_and_no_was_price():
    html = """
    <!doctype html>
    <html>
      <head><title>Ovo Ember Trail Shoe — Shield Outfitters</title></head>
      <body>
        <script>
          window.__STATE__={"product":{"id":"SH-CUSTOM-2","title":"Ovo Ember Trail Shoe","offer":{"amount":94459,"currency":"GBP","was":null,"stock":"OUT_OF_STOCK"}}};
        </script>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)
    obs = extract_shield(mock_client, "shield", "http://localhost:4000/stores/shield/item/SH-CUSTOM-2", html)

    assert obs.name == "Ovo Ember Trail Shoe"
    assert obs.price_cents == 94459
    assert obs.currency == "GBP"
    assert obs.compare_at_cents is None
    assert obs.availability == "out_of_stock"
    assert obs.notes == []


def test_shield_window_state_catalog_prices_map():
    html = """
    <!doctype html>
    <html>
      <body>
        <script>
          window.__STATE__={"prices":{"ITEM-99":{"amount":126836,"currency":"GBP"}}};
        </script>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)
    obs = extract_shield(mock_client, "shield", "http://localhost:4000/stores/shield/item/ITEM-99", html)

    assert obs.product_id == "ITEM-99"
    assert obs.price_cents == 126836
    assert obs.currency == "GBP"
    assert obs.availability == "in_stock"


def test_shield_http_429_retry_after_and_bounded_retries():
    client = Client(retries=2)

    resp_429 = MagicMock(spec=requests.Response)
    resp_429.status_code = 429
    resp_429.text = "Too Many Requests"
    resp_429.headers = {"Retry-After": "0.1"}

    resp_200 = MagicMock(spec=requests.Response)
    resp_200.status_code = 200
    resp_200.text = "OK"

    # First request returns 429, second returns 200
    with patch.object(client.session, "request", side_effect=[resp_429, resp_200]) as mock_req, patch("time.sleep") as mock_sleep:
        r = client.get("http://localhost:4000/stores/shield/item/ITEM-429")
        assert r.status_code == 200
        assert mock_req.call_count == 2
        assert mock_sleep.call_count >= 1
        assert pytest.approx(mock_sleep.call_args[0][0], abs=1e-3) == 0.1



def test_shield_bounded_retries_exhaustion():
    client = Client(retries=2)

    resp_429 = MagicMock(spec=requests.Response)
    resp_429.status_code = 429
    resp_429.text = "Too Many Requests"
    resp_429.headers = {"Retry-After": "0.1"}

    with patch.object(client.session, "request", return_value=resp_429) as mock_req, patch("time.sleep"):
        r = client.get("http://localhost:4000/stores/shield/item/ITEM-429")
        assert r.status_code == 429
        assert mock_req.call_count == 3  # 1 initial + 2 retries


def test_shield_malformed_response_handling():
    html = """
    <html>
      <head><title>Corrupted Page</title></head>
      <body>
        <script>window.__STATE__={invalid_json</script>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)
    obs = extract_shield(mock_client, "shield", "http://localhost:4000/stores/shield/item/CORRUPT-1", html)

    assert obs.product_id == "CORRUPT-1"
    assert obs.price_cents is None
    assert obs.notes == ["shield extraction failed"]


def test_shield_parse_retry_after_http_date_and_numeric():
    client = Client()
    assert client._parse_retry_after("1.5") == 1.5
    assert client._parse_retry_after("5") == 5.0
    assert client._parse_retry_after(None) is None
    assert client._parse_retry_after("invalid") is None

    # Test HTTP-date in the past returns 0.0
    past_date = "Wed, 21 Oct 2015 07:28:00 GMT"
    val = client._parse_retry_after(past_date)
    assert val is not None
    assert val == 0.0


def test_shield_rate_limit_budget_bounded():
    client = Client(retries=2)

    resp_429 = MagicMock(spec=requests.Response)
    resp_429.status_code = 429
    resp_429.text = "Too Many Requests"
    resp_429.headers = {"Retry-After": "0.01"}

    with patch.object(client.session, "request", return_value=resp_429) as mock_req, patch("time.sleep"):
        r = client.get("http://localhost:4000/stores/shield/item/ITEM-429-BUDGET")
        assert r.status_code == 429
        # Bounded at retries + 1 calls (1 initial attempt + 2 retries)
        assert mock_req.call_count == 3


def test_shield_sequential_429_with_retry_after_succeeds():
    client = Client(retries=3)

    resp_429_1 = MagicMock(spec=requests.Response)
    resp_429_1.status_code = 429
    resp_429_1.text = "Too Many Requests"
    resp_429_1.headers = {"Retry-After": "0.02"}

    resp_429_2 = MagicMock(spec=requests.Response)
    resp_429_2.status_code = 429
    resp_429_2.text = "Too Many Requests"
    resp_429_2.headers = {"Retry-After": "0.02"}

    resp_200 = MagicMock(spec=requests.Response)
    resp_200.status_code = 200
    resp_200.text = "<html><body><h1>Success Product</h1></body></html>"

    sleep_calls = []

    def fake_sleep(dur):
        sleep_calls.append(dur)

    with patch.object(client.session, "request", side_effect=[resp_429_1, resp_429_2, resp_200]) as mock_req, \
         patch("time.sleep", side_effect=fake_sleep):
        r = client.get("http://localhost:4000/stores/shield/item/seq_test")
        assert r.status_code == 200
        assert mock_req.call_count == 3
        assert len(sleep_calls) >= 2


def test_shield_retry_after_delay_applied_before_retry():
    import time
    client = Client(retries=2)

    resp_429 = MagicMock(spec=requests.Response)
    resp_429.status_code = 429
    resp_429.text = "Too Many Requests"
    resp_429.headers = {"Retry-After": "0.15"}

    resp_200 = MagicMock(spec=requests.Response)
    resp_200.status_code = 200
    resp_200.text = "OK"

    timestamps = []

    def fake_request(method, url, **kwargs):
        timestamps.append(time.monotonic())
        if len(timestamps) == 1:
            return resp_429
        return resp_200

    with patch.object(client.session, "request", side_effect=fake_request):
        r = client.get("http://localhost:4000/stores/shield/item/delay_test")
        assert r.status_code == 200
        assert len(timestamps) == 2
        # Delay of 0.15s must elapse before the second request is sent (allowing Windows timer tick granularity)
        assert timestamps[1] - timestamps[0] >= 0.12



