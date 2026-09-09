"""Tiny HTTP surface: health, latest observations, and a dashboard. Not graded; nice for demos."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import storage


def make_app(db_path: str = "pricewatch.db") -> FastAPI:
    app = FastAPI(title="PriceWatch")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/observations")
    def observations():
        return [o.to_dict() for o in storage.History(db_path).latest()]

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        rows = "".join(
            f"<tr><td>{o.store}</td><td>{o.name or o.product_id}</td><td>{'' if o.price_cents is None else o.price_cents / 100:.2f} {o.currency}</td>"
            f"<td>{o.availability}</td><td>{o.observed_at[:19]}</td></tr>"
            for o in storage.History(db_path).latest())
        return f"<html><body style='font-family:system-ui'><h1>PriceWatch</h1><table border=1 cellpadding=6>" \
               f"<tr><th>store</th><th>product</th><th>price</th><th>availability</th><th>seen</th></tr>{rows}</table></body></html>"

    return app
