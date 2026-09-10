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
    assert o.compare_at_cents == 93720
    assert o.availability == "in_stock"


def test_maple_regular_item():
    html = """<html><body><div class="product"><h1 class="product__title">Regular Pen</h1>
    <div class="price"><span class="price">15,50 €</span></div>
    <p class="muted">In stock</p></div></body></html>"""
    o = extract_maple(Client(), "maple", "http://x/stores/maple/products/regular-pen", html)
    assert o.price_cents == 1550
    assert o.currency == "EUR"
    assert o.compare_at_cents is None
    assert o.availability == "in_stock"


def test_maple_out_of_stock_item():
    html = """<html><body><div class="product"><h1 class="product__title">Sold Out Item</h1>
    <div class="price"><span class="price">49,99 €</span></div>
    <p class="muted">Sold out</p></div></body></html>"""
    o = extract_maple(Client(), "maple", "http://x/stores/maple/products/sold-out", html)
    assert o.price_cents == 4999
    assert o.availability == "out_of_stock"

