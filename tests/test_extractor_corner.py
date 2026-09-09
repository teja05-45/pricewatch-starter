from pricewatch.agents.extractor import extract_corner
from pricewatch.http import Client

HTML = """<html><head><script type="application/ld+json">{"@type":"Product","name":"Aurel Nordic Kettle","sku":"ABC123",
"offers":{"@type":"Offer","price":"596.85","priceCurrency":"USD","availability":"https://schema.org/InStock"}}</script></head>
<body><h1>Aurel Nordic Kettle</h1><p><s>$938.56</s> <strong class="price">$596.85</strong></p></body></html>"""


def test_corner_sale_item():
    o = extract_corner(Client(), "corner", "http://x/stores/corner/p/ABC123", HTML)
    assert o.price_cents == 59685 and o.currency == "USD" and o.compare_at_cents == 93856 and o.availability == "in_stock"
