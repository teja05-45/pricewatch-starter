"""LLM extractor: fallback for un-adaptered stores.

Integrates pre-mining evidence extraction, LLM semantic selection, schema validation,
and deterministic post-validation overrides.
"""
from __future__ import annotations

import json
import re
from typing import Any
from bs4 import BeautifulSoup

from ..models import Observation
from ..providers import Provider
from .normalizer import detect_currency, parse_money, ZERO_DECIMAL_CURRENCIES

SYSTEM = """You extract structured product offer data from e-commerce product pages based on semantic evidence.
Respond ONLY with a valid JSON object matching the required schema below. No markdown code blocks, no preamble, no extra text.

Required JSON Schema:
{
  "name": str | null,
  "price_reason": str | null,
  "price_cents": int | null,
  "currency": str | null,
  "availability": "in_stock" | "out_of_stock" | "unknown",
  "pack_size": int,
  "compare_at_cents": int | null
}

Critical Generic Price-Selection Rules:
1. "price_cents": The TOTAL CURRENT SELLING PRICE the customer pays to purchase the product/pack today, expressed in minor currency units (cents, öre, paise, yen).
   - DO NOT SELECT: Monthly EMI/financing installments (e.g., "₹2,439/month", "x months", "per month"), interest, shipping, taxes, deposits, or gift cards.
   - Example: If a page displays "₹29,260" selling price and "₹2,439/mo EMI", select 2926000 cents (₹29,260.00), NOT 243900 cents.
   - Example: If a page displays "₹99,398" total pack price and "₹33,133 per unit", select 9939800 cents (₹99,398.00), NOT 3313300 cents.
   - DO NOT SELECT: Struck-through list/MSRP prices as price_cents. If "₹35,000" is list price and "₹29,260" is current sale price, price_cents MUST be 2926000 (and compare_at_cents MUST be 3500000).
   - Currency minor units rule:
     * Standard 2-decimal currencies (USD, EUR, GBP, NOK, SEK, DKK, INR, CAD, AUD, CHF): Multiply main units by 100.
       e.g., 2926 NOK = 292600; 129.90 INR = 12990; $19.99 = 1999.
     * Zero-decimal currencies (JPY): Do NOT multiply by 100.
       e.g., 1500 JPY = 1500.

2. "currency": 3-letter ISO-4217 code (e.g. INR, NOK, USD, EUR, GBP, SEK, DKK, JPY, CAD, AUD, CHF).
   - Infer from symbol if unambiguous: ₹ -> INR, kr -> NOK (or SEK/DKK based on text/domain), $ -> USD, € -> EUR, £ -> GBP, ¥ -> JPY.

3. "availability":
   - "in_stock": Look for "in stock", "available", "buy now", "add to cart", "legg i handlekurv", "kjøp", "på lager".
   - "out_of_stock": Look for "out of stock", "sold out", "currently unavailable", "midlertidig utsolgt", "ikke på lager", "utsolgt".
   - "unknown": Only if no availability signal is present.
   - Note: Availability must reflect stock status independently of whether a price is displayed.

4. "pack_size": Total count/quantity of physical units in the item package (default 1).
   - Look for "Pack of X", "X-pack", "Set of X", "X count", "X pieces", "X-pakning", "X stk".
   - DO NOT confuse screen size (e.g., 55"), dimensions, model numbers, storage capacity, or EMI months with pack size.

5. "compare_at_cents": Struck-through original MSRP / list price if on sale, converted to minor units; null if not on sale.
"""


def premine_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # 1. Structured Data (JSON-LD)
    structured_data = []
    for s in soup.find_all("script", type=lambda t: t and ("ld+json" in t or "json" in t)):
        txt = s.get_text().strip()
        if txt and ("price" in txt.lower() or "offer" in txt.lower() or "product" in txt.lower()):
            try:
                data = json.loads(txt)
                structured_data.append(data)
            except Exception:
                if len(txt) < 1000:
                    structured_data.append(txt)

    # 2. Meta Tags & Itemprops
    meta_data = {}
    for m in soup.find_all("meta"):
        name = m.get("name") or m.get("property") or m.get("itemprop")
        content = m.get("content")
        if name and content and any(k in str(name).lower() for k in ["price", "currency", "avail", "stock", "title", "product"]):
            meta_data[str(name)] = str(content)

    # Clean text container
    for tag in soup(["style", "svg", "iframe", "noscript"]):
        tag.decompose()

    full_text = soup.get_text(" ", strip=True)

    # 3. Action Buttons & Availability signals
    in_stock_keywords = ["add to cart", "buy now", "in stock", "kjøp", "legg i handlekurv", "på lager", "tilgjengelig", "in den warenkorb"]
    out_of_stock_keywords = ["out of stock", "sold out", "currently unavailable", "utsolgt", "ikke på lager", "midlertidig utsolgt", "nicht auf lager"]

    found_in_stock = [kw for kw in in_stock_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text, re.IGNORECASE)]
    found_out_of_stock = [kw for kw in out_of_stock_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text, re.IGNORECASE)]

    # 4. Pack size candidates
    pack_matches = re.findall(r"\b(\d+)\s*[-]?\s*(?:pack|pk|pakning|stk|pieces|items|count|set)\b|\b(?:pack|set|pakning|stk)\s*of\s*(\d+)\b", full_text, re.IGNORECASE)
    pack_candidates = []
    for m in pack_matches:
        num = m[0] or m[1]
        if num and 1 <= int(num) <= 100:
            pack_candidates.append(int(num))

    # 5. Price candidates with surrounding context
    price_pattern = re.compile(
        r"(?:(?:[₹$€£¥]\s*[\d\s.,]+)|(?:(?:kr|NOK|SEK|DKK|INR|USD|EUR|GBP|JPY|Rs\.?)\s*[\d\s.,]+)|(?:[\d\s.,]+\s*(?:kr|NOK|SEK|DKK|INR|USD|EUR|GBP|JPY|Rs\.?)))",
        re.IGNORECASE
    )

    candidates = []
    seen_vals = set()

    for elem in soup.find_all(True):
        if elem.find_all(True):
            continue
        text_snippet = elem.get_text(" ", strip=True)
        if not text_snippet:
            continue

        for match in price_pattern.finditer(text_snippet):
            raw_val = match.group(0).strip()
            if raw_val in seen_vals:
                continue
            seen_vals.add(raw_val)

            parent_text = elem.parent.get_text(" ", strip=True) if elem.parent else text_snippet
            is_crossed = elem.name in ["s", "del", "strike"] or "line-through" in str(elem.get("style", "")) or "old" in str(elem.get("class", "")) or "struck" in str(elem.get("class", ""))
            is_emi = bool(re.search(r"\b(?:emi|mo|mnd|month|monthly|per month|/mo|/mnd)\b", parent_text, re.IGNORECASE))
            is_unit = bool(re.search(r"\b(?:per unit|per item|per piece|pr stk|per stk|/unit|/item)\b", parent_text, re.IGNORECASE))
            is_list = bool(re.search(r"\b(?:msrp|rrp|list|was|original|før|førpris|compare)\b", parent_text, re.IGNORECASE))
            is_big = "big" in str(elem.get("class", "")) or "price" in str(elem.get("class", ""))

            candidates.append({
                "value": raw_val,
                "context": parent_text[:120],
                "is_crossed_out": is_crossed,
                "is_emi": is_emi,
                "is_unit": is_unit,
                "is_list": is_list,
                "is_main_heading": is_big,
            })

    return {
        "structured_data": structured_data[:2],
        "meta_data": meta_data,
        "in_stock_signals": found_in_stock,
        "out_of_stock_signals": found_out_of_stock,
        "pack_candidates": pack_candidates,
        "price_candidates": candidates[:8],
        "text_summary": full_text[:4000],
    }


def parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Attempt 1: Direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Extract JSON object substring via regex
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        sub = m.group(1).strip()
        try:
            return json.loads(sub)
        except json.JSONDecodeError:
            # Attempt 3: Robust cleanup of trailing commas & control chars
            cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sub)
            cleaned = re.sub(r",\s*([\}\]])", r"\1", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    # Attempt 4: Fallback regex field extraction
    fallback_data = {}
    name_m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
    if name_m:
        fallback_data["name"] = name_m.group(1)

    price_m = re.search(r'"price_cents"\s*:\s*(\d+)', text)
    if price_m:
        fallback_data["price_cents"] = int(price_m.group(1))

    curr_m = re.search(r'"currency"\s*:\s*"([A-Z]{3})"', text, re.IGNORECASE)
    if curr_m:
        fallback_data["currency"] = curr_m.group(1).upper()

    avail_m = re.search(r'"availability"\s*:\s*"(in_stock|out_of_stock|unknown)"', text, re.IGNORECASE)
    if avail_m:
        fallback_data["availability"] = avail_m.group(1).lower()

    pack_m = re.search(r'"pack_size"\s*:\s*(\d+)', text)
    if pack_m:
        fallback_data["pack_size"] = int(pack_m.group(1))

    if fallback_data:
        return fallback_data

    return json.loads(text)


def extract_with_llm(provider: Provider, store: str, url: str, html: str, timeout: float = 30.0) -> Observation:
    premined = premine_html(html)
    
    user_prompt = (
        f"URL: {url}\n\n"
        f"PREMINED EVIDENCE:\n"
        f"- Structured Data: {json.dumps(premined['structured_data'])}\n"
        f"- Meta Data: {json.dumps(premined['meta_data'])}\n"
        f"- In-Stock Signals: {json.dumps(premined['in_stock_signals'])}\n"
        f"- Out-Of-Stock Signals: {json.dumps(premined['out_of_stock_signals'])}\n"
        f"- Pack Candidates: {json.dumps(premined['pack_candidates'])}\n"
        f"- Price Candidates: {json.dumps(premined['price_candidates'])}\n\n"
        f"PAGE TEXT:\n{premined['text_summary']}"
    )

    pid = url.rstrip("/").split("/")[-1]

    raw = provider.complete(SYSTEM, user_prompt, metadata={"source_url": url, "store": store}, timeout=timeout)
    data = parse_llm_json(raw)

    # 1. Normalize Name
    name = str(data.get("name") or "").strip()

    # 2. Normalize Currency
    currency = data.get("currency")
    if currency:
        currency = str(currency).upper().strip()
    if not currency or len(currency) != 3:
        currency = detect_currency(premined['text_summary'], "USD") or "USD"

    # 3. Normalize Price Cents
    price_cents = data.get("price_cents")
    if price_cents is not None:
        try:
            price_cents = int(price_cents)
            if price_cents < 0:
                price_cents = None
        except (ValueError, TypeError):
            price_cents = None

    # Deterministic Override Guard for EMI / Monthly / Unit traps
    if price_cents is not None and premined["price_candidates"]:
        # Find candidates flagged as main selling price vs EMI/unit
        selling_candidates = [c for c in premined["price_candidates"] if not c["is_emi"] and not c["is_unit"] and not c["is_crossed_out"] and not c["is_list"]]
        emi_candidates = [c for c in premined["price_candidates"] if c["is_emi"]]
        
        # Check if model accidentally selected an EMI candidate price
        if emi_candidates and selling_candidates:
            for emi_c in emi_candidates:
                parsed_emi, _ = parse_money(emi_c["value"], currency)
                if parsed_emi and price_cents in (parsed_emi, parsed_emi * 100):
                    # Override with main selling price candidate!
                    for sell_c in selling_candidates:
                        parsed_sell, _ = parse_money(sell_c["value"], currency)
                        if parsed_sell:
                            price_cents = parsed_sell
                            break

    # 4. Compare-At Cents
    compare_at_cents = data.get("compare_at_cents")
    if compare_at_cents is not None:
        try:
            compare_at_cents = int(compare_at_cents)
            if compare_at_cents < 0:
                compare_at_cents = None
        except (ValueError, TypeError):
            compare_at_cents = None

    # 5. Availability Normalization & Deterministic Guard
    avail = str(data.get("availability") or "unknown").lower().strip()
    if premined["out_of_stock_signals"] and not premined["in_stock_signals"]:
        avail = "out_of_stock"
    elif premined["in_stock_signals"] and not premined["out_of_stock_signals"]:
        avail = "in_stock"
    elif avail not in ("in_stock", "out_of_stock", "unknown"):
        avail = "unknown"

    # 6. Pack Size Normalization & Deterministic Guard
    try:
        pack_size = int(data.get("pack_size") or 1)
        if pack_size < 1:
            pack_size = 1
    except (ValueError, TypeError):
        pack_size = 1

    if premined["pack_candidates"] and pack_size == 1:
        # Override if preminer found explicit pack candidate (e.g., Pack of 3 -> 3)
        pack_size = premined["pack_candidates"][0]

    return Observation(
        store=store,
        product_id=pid,
        url=url,
        name=name,
        price_cents=price_cents,
        currency=currency,
        compare_at_cents=compare_at_cents,
        availability=avail,
        pack_size=pack_size,
        source="llm",
    )
