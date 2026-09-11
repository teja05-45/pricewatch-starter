"""Normalizer agent: turns whatever a page printed into (minor units, ISO currency).

Storefronts print money in a dozen ways. Everything downstream (history, alerts, the
dashboard) assumes `price_cents` is an int in the store's currency. This is the only place
that should know about currency symbols and locale formatting.
"""
from __future__ import annotations

import re
from typing import Optional

SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "kr": "SEK",
    "¥": "JPY",
    "CHF": "CHF",
}
CODES = {"USD", "EUR", "GBP", "INR", "SEK", "NOK", "DKK", "JPY", "CHF", "CAD", "AUD"}
ZERO_DECIMAL_CURRENCIES = {"JPY"}


def detect_currency(text: str, default: Optional[str] = None) -> Optional[str]:
    if not text:
        return default
    t = text.strip()
    for code in CODES:
        if re.search(rf"\b{code}\b", t, re.IGNORECASE):
            return code
    for sym, code in sorted(SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if sym in t:
            return code
    return default


def parse_money(text: str | None, default_currency: Optional[str] = None) -> tuple[Optional[int], Optional[str]]:
    """Parse a printed price like "$1,299.00" or "937,20 €" into (cents, currency).

    Returns (None, currency) when no number is present.
    """
    if text is None:
        return None, default_currency
    currency = detect_currency(text, default_currency)

    # Clean text to find the main numeric block
    # Remove non-breaking spaces, collapse spaces around punctuation, simplify whitespace
    clean_text = text.replace("\xa0", " ").strip()
    clean_text = re.sub(r"\s*([.,])\s*", r"\1", clean_text)

    # Find candidate number pattern with digits, commas, periods, spaces
    # Example: 1,299.00 or 937,20 or 1.299,00 or 1 299,00 or 596
    m = re.search(r"(\d+(?:[\s.,]\d+)*)", clean_text)
    if not m:
        return None, currency

    num_str = m.group(1).replace(" ", "")
    if not num_str:
        return None, currency

    # Determine decimal vs thousands separator
    if "." in num_str and "," in num_str:
        if num_str.find(".") < num_str.find(","):
            # European: 1.299,00 -> 1299.00
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            # US: 1,299.00 -> 1299.00
            num_str = num_str.replace(",", "")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            # Decimal comma: 937,20 or 720,92 -> 937.20
            num_str = parts[0] + "." + parts[1]
        else:
            # Thousands comma: 1,000,000 -> 1000000
            num_str = num_str.replace(",", "")
    elif "." in num_str:
        parts = num_str.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and (currency in ("EUR", "SEK", "NOK", "DKK")):
            # Ambiguous: e.g. 1.000 EUR with no decimals could be 1000
            # Check if it's 3 digits thousands separator
            num_str = "".join(parts)
        else:
            # Standard decimal: 596.85
            pass

    try:
        amount = float(num_str)
    except ValueError:
        return None, currency

    if currency in ZERO_DECIMAL_CURRENCIES:
        return int(round(amount)), currency

    return int(round(amount * 100)), currency


def unit_price(price_cents: Optional[int], pack_size: int) -> Optional[int]:
    if price_cents is None or pack_size <= 1:
        return None
    return int(round(price_cents / pack_size))

