"""LLM extractor: the fallback for stores we have no adapter for.

Given raw HTML and its URL, ask a model for the structured offer. This is deliberately
minimal — it is the starting point for Stage 3, not the answer to it.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Observation
from ..providers import Provider

SYSTEM = """You extract e-commerce offer data from a product page and answer ONLY with a JSON object:
{"name": str|null, "price_cents": int|null, "currency": "ISO-4217"|null, "availability": "in_stock"|"out_of_stock"|"unknown",
 "pack_size": int, "compare_at_cents": int|null}
price_cents is the price of the pack actually being sold, in minor units. If there is no price, use null."""


def clean_html(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    return text[:limit]


def extract_with_llm(provider: Provider, store: str, url: str, html: str, timeout: float = 30.0) -> Observation:
    user = f"URL: {url}\n\nPAGE TEXT:\n{clean_html(html)}"
    raw = provider.complete(SYSTEM, user, metadata={"source_url": url, "store": store}, timeout=timeout)
    data = json.loads(raw)
    return Observation(
        store=store, product_id=url.rstrip("/").split("/")[-1], url=url, name=data.get("name") or "",
        price_cents=data.get("price_cents"), currency=data.get("currency") or "",
        compare_at_cents=data.get("compare_at_cents"), availability=data.get("availability") or "unknown",
        pack_size=int(data.get("pack_size") or 1), source="llm",
    )
