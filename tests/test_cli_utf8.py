import tempfile
from pathlib import Path
from pricewatch.cli import main
from pricewatch.http import Client
from pricewatch.agents.extractor import extract_corner


def test_cli_extract_utf8_file(tmp_path):
    html_content = """<html><head><script type="application/ld+json">
    {"@type":"Product","name":"Special Item — Premium Edition € ₹","sku":"UTF8-TEST",
    "offers":{"@type":"Offer","price":"129.99","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}
    </script></head><body><h1>Special Item — Premium Edition € ₹</h1></body></html>"""

    html_file = tmp_path / "product_utf8.html"
    html_file.write_text(html_content, encoding="utf-8")

    # Command line invocation reading local utf-8 html file
    exit_code = main(["extract", "--url", "http://localhost:4000/stores/corner/p/UTF8-TEST", "--html", str(html_file)])
    assert exit_code == 0


def test_corner_extractor_utf8():
    html_content = """<html><head><script type="application/ld+json">
    {"@type":"Product","name":"Nordic Chair — Teak & Leather €","sku":"CORNER-UTF8",
    "offers":{"@type":"Offer","price":"250.00","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}
    </script></head><body><h1>Nordic Chair — Teak & Leather €</h1></body></html>"""

    o = extract_corner(Client(), "corner", "http://localhost:4000/stores/corner/p/CORNER-UTF8", html_content)
    assert o.name == "Nordic Chair — Teak & Leather €"
    assert o.price_cents == 25000
    assert o.currency == "EUR"
