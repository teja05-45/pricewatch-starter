import hashlib
import json
from unittest.mock import MagicMock

import pytest

from pricewatch.agents.extractor import extract_flux, _parse_flux_bundle
from pricewatch.http import Client


def test_flux_bundle_parsing_secret_and_sig_len():
    bundle_js = """
    !function(){
        var _0x1=["fx_3ad94d","3a18a937cf44b6"],_0x2=String.fromCharCode(124),_0x3=40,_0x4="SHA-256";
        async function _0x6(e){
            var t=(await _0x5(_0x1.join("")+_0x2+e)).slice(0,_0x3);
        }
    }();
    """
    secret, sig_len, algo = _parse_flux_bundle(bundle_js)
    assert secret == "fx_3ad94d3a18a937cf44b6"
    assert sig_len == 40

    sku = "FLX-TEST-001"
    raw_input = f"{secret}|{sku}"
    sig = hashlib.sha256(raw_input.encode("utf-8")).hexdigest()[:sig_len]
    assert len(sig) == 40
    assert sig == hashlib.sha256(b"fx_3ad94d3a18a937cf44b6|FLX-TEST-001").hexdigest()[:40]


def test_flux_pdp_and_bundle_discovery_graphql_call():
    html = """
    <!doctype html>
    <html>
      <head>
        <meta name="flux-build" content="b33e8533e">
      </head>
      <body>
        <div class="pdp" data-sku="FLX-5Y6AJE">
          <h1>Aurel Ember Espresso Grinder</h1>
        </div>
        <script src="/stores/flux/bundle.js"></script>
      </body>
    </html>
    """

    mock_client = MagicMock(spec=Client)

    # Mock bundle response
    mock_bundle_resp = MagicMock()
    mock_bundle_resp.status_code = 200
    mock_bundle_resp.text = 'var _0x1=["fx_3ad94d","3a18a937cf44b6"],_0x3=40;'
    mock_client.get.return_value = mock_bundle_resp

    # Mock GraphQL response
    mock_gql_resp = MagicMock()
    mock_gql_resp.status_code = 200
    mock_gql_resp.json.return_value = {
        "data": {
            "product": {
                "sku": "FLX-5Y6AJE",
                "title": "Aurel Ember Espresso Grinder",
                "offer": {
                    "amount": 46122,
                    "unit": "minor",
                    "currency": "USD",
                    "stock": "IN_STOCK",
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_gql_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/item/FLX-5Y6AJE", html)

    assert obs.store == "flux"
    assert obs.product_id == "FLX-5Y6AJE"
    assert obs.name == "Aurel Ember Espresso Grinder"
    assert obs.price_cents == 46122
    assert obs.currency == "USD"
    assert obs.availability == "in_stock"
    assert obs.notes == []

    # Verify bundle fetch
    mock_client.get.assert_called_once_with("http://localhost:4000/stores/flux/bundle.js")

    # Verify GraphQL call headers and signature
    mock_client.post.assert_called_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert call_args[0] == "http://localhost:4000/stores/flux/api/graphql"
    headers = call_kwargs["headers"]
    assert headers["x-flux-build"] == "b33e8533e"

    expected_sig = hashlib.sha256(b"fx_3ad94d3a18a937cf44b6|FLX-5Y6AJE").hexdigest()[:40]
    assert headers["x-flux-sig"] == expected_sig


def test_flux_graphql_major_units():
    html = '<div class="pdp" data-sku="FX-101"></div><meta name="flux-build" content="b-12345">'

    mock_client = MagicMock(spec=Client)
    mock_bundle_resp = MagicMock()
    mock_bundle_resp.status_code = 200
    mock_bundle_resp.text = 'var _0x1=["fx_3ad94d","3a18a937cf44b6"];'
    mock_client.get.return_value = mock_bundle_resp

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
                    "stock": "IN_STOCK",
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-101", html)

    assert obs.price_cents == 4999
    assert obs.currency == "USD"
    assert obs.availability == "in_stock"


def test_flux_graphql_minor_units_and_stale():
    html = '<div class="pdp" data-sku="FX-102"></div><meta name="flux-build" content="v2.1">'
    mock_client = MagicMock(spec=Client)
    mock_bundle_resp = MagicMock()
    mock_bundle_resp.status_code = 200
    mock_bundle_resp.text = 'var _0x1=["fx_3ad94d","3a18a937cf44b6"];'
    mock_client.get.return_value = mock_bundle_resp

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
                    "stock": "IN_STOCK",
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
    mock_bundle_resp = MagicMock()
    mock_bundle_resp.status_code = 200
    mock_bundle_resp.text = ''
    mock_client.get.return_value = mock_bundle_resp

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
                    "stock": "OUT_OF_STOCK",
                    "stale": False,
                },
            }
        }
    }
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-103", html)

    assert obs.availability == "out_of_stock"


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
    mock_bundle_resp = MagicMock()
    mock_bundle_resp.status_code = 404
    mock_client.get.return_value = mock_bundle_resp

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_client.post.return_value = mock_resp

    obs = extract_flux(mock_client, "flux", "http://localhost:4000/stores/flux/products/FX-FALLBACK", html)

    assert obs.product_id == "FX-FALLBACK"
    assert obs.name == "Flux Desk Mat"
    assert obs.price_cents == 1599
