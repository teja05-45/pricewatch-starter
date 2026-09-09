"""Reproduces one symptom from tasks/ISSUE-1.md. It fails on the starter. Make it pass — and then keep going."""
from pricewatch.agents.extractor import extract_maple
from pricewatch.http import Client

HTML = """<html><body><div class="product"><h1 class="product__title">Kestrel Lumen Notebook</h1>
<div class="price"><span class="price price--compare"><s>937,20 €</s></span> <span class="price price--sale">720,92 €</span></div>
<p class="muted">In stock · prices shown in EUR</p></div></body></html>"""


def test_maple_sale_item_reports_sale_price():
    o = extract_maple(Client(), "maple", "http://x/stores/maple/products/kestrel-lumen-notebook", HTML)
    assert o.price_cents == 72092
    assert o.currency == "EUR"
