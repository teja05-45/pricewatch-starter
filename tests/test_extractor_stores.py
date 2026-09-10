from pricewatch.agents.extractor import extract_zon, extract_shield, extract_flux
from pricewatch.http import Client


def test_zon_dynamic_extraction():
    html = """<html><body>
    <div class="product">
        <h1 class="a-affa10">Premium Organic Coffee Beans (Pack of 3)</h1>
        <div class="a-1c3f89"><span class="a-2b2181">29</span><span class="a-4e2865">99</span></div>
        <div class="a-78b7d1">In Stock</div>
    </div>
    </body></html>"""
    o = extract_zon(Client(), "zon", "http://x/stores/zon/dp/coffee-beans", html)
    assert o.price_cents == 2999
    assert o.currency == "USD"
    assert o.pack_size == 3
    assert o.unit_price_cents == 1000
    assert o.availability == "in_stock"


def test_shield_challenge_and_extraction():
    html = """<html><body>
    <div class="item">
        <h1 class="product-title">Tactical Rucksack 45L</h1>
        <div class="current-price" data-price="89.99">£89.99</div>
        <div class="availability">In Stock</div>
    </div>
    </body></html>"""
    o = extract_shield(Client(), "shield", "http://x/stores/shield/item/rucksack", html)
    assert o.price_cents == 8999
    assert o.currency == "GBP"
    assert o.availability == "in_stock"


def test_flux_spa_json_script_extraction():
    html = """<html><body>
    <script type="application/json">
    {"product": {"name": "Flux Mechanical Keyboard", "price": 149.99, "currency": "USD", "in_stock": true}}
    </script>
    </body></html>"""
    o = extract_flux(Client(), "flux", "http://x/stores/flux/item/keyboard", html)
    assert o.price_cents == 14999
    assert o.currency == "USD"
    assert o.availability == "in_stock"
