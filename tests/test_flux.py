import hashlib
import json
from unittest.mock import MagicMock

import pytest

from pricewatch.agents.extractor import extract_flux
from pricewatch.http import Client


def test_flux_signature_generation():
    sku = "fx-prod-999"
    expected_sig_raw = f"fx_1b11e1e8cfb25a950a27|{sku}"
    expected_sig = hashlib.sha256(expected_sig_raw.encode("utf-8")).hexdigest()[:24]

    assert len(expected_sig) == 24
    assert expected_sig == hashlib.sha256(b"fx_1b11e1e8cfb25a950a27|fx-prod-999").hexdigest()[:24]


def test_flux_graphql_major_units():
    html = """
    <html>
      <head>
        <meta name="flux-build" content="b-12345">
      </head>
      <body>
        <div class="pdp" data-sku="FX-101">
          <span class="pdp__price"></span>
        </div>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "product": {
                "sku": "FX-101",
                "title": "Flux Wireless Headphones",
                "offer": {
                    "amount": 49.99,
                    "unit": "major",
                    "currency": "USD",
                    "stock": True,
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-101", html)

    assert obs.store == "flux"
    assert obs.product_id == "FX-101"
    assert obs.name == "Flux Wireless Headphones"
    assert obs.price_cents == 4999
    assert obs.currency == "USD"
    assert obs.availability == "in_stock"
    assert obs.notes == []

    # Verify GraphQL call structure
    mock_client.post.assert_called_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert call_args[0] == "http://localhost:4000/stores/flux/api/graphql"
    headers = call_kwargs["headers"]
    assert headers["x-flux-build"] == "b-12345"

    expected_sig = hashlib.sha256(b"fx_1b11e1e8cfb25a950a27|FX-101").hexdigest()[:24]
    assert headers["x-flux-sig"] == expected_sig


def test_flux_graphql_minor_units_and_stale():
    html = '<div class="pdp" data-sku="FX-102"></div><meta name="flux-build" content="v2.1">'
    mock_client = MagicMock(spec=Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "product": {
                "sku": "FX-102",
                "title": "Flux Gaming Mouse",
                "offer": {
                    "amount": 2500,
                    "unit": "minor",
                    "currency": "EUR",
                    "stock": True,
                    "stale": True,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-102", html)

    assert obs.product_id == "FX-102"
    assert obs.name == "Flux Gaming Mouse"
    assert obs.price_cents == 2500
    assert obs.currency == "EUR"
    assert obs.notes == ["stale price"]


def test_flux_graphql_out_of_stock():
    html = '<div class="pdp" data-sku="FX-103"></div>'
    mock_client = MagicMock(spec=Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "product": {
                "sku": "FX-103",
                "title": "Flux Mechanical Keyboard",
                "offer": {
                    "amount": 8900,
                    "unit": "minor",
                    "currency": "USD",
                    "stock": False,
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-103", html)

    assert obs.availability == "out_of_stock"


def test_flux_graphql_jpy():
    html = '<div class="pdp" data-sku="FX-JPY"></div>'
    mock_client = MagicMock(spec=Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "product": {
                "sku": "FX-JPY",
                "title": "Flux Tokyo Edition",
                "offer": {
                    "amount": 3500,
                    "unit": "major",
                    "currency": "JPY",
                    "stock": True,
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-JPY", html)

    assert obs.price_cents == 3500
    assert obs.currency == "JPY"


def test_flux_fallback_script_tags():
    html = """
    <html>
      <body>
        <h1>Flux Desk Mat</h1>
        <script>
          {"product": {"name": "Flux Desk Mat", "price": 1599}}
        </script>
      </body>
    </html>
    """
    mock_client = MagicMock(spec=Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 500  # GraphQL fails
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-FALLBACK", html)

    assert obs.product_id == "FX-FALLBACK"
    assert obs.name == "Flux Desk Mat"
    assert obs.price_cents == 1599
