"""Extractor agent: one adapter per storefront turns a fetched page into an Observation.

Adapters receive the raw HTML (already fetched by the Client) and the URL. They must not do
their own networking except through the Client they are given, so throttling and cookies
stay in one place.

Adapters are registered by name; `stores.yaml` maps each store to an adapter.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http import Client
from ..models import Observation
from .normalizer import parse_money, unit_price

ADAPTERS: dict[str, Callable[[Client, str, str, str], Observation]] = {}


def adapter(name: str):
    def deco(fn):
        ADAPTERS[name] = fn
        return fn
    return deco


def _pid_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


# --------------------------------------------------------------------------- Level 1: Corner
@adapter("corner")
def extract_corner(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    ld = soup.find("script", type="application/ld+json")
    data = {}
    if ld and ld.string:
        try:
            data = json.loads(ld.string)
        except json.JSONDecodeError:
            data = {}

    offer = data.get("offers", {}) if isinstance(data.get("offers"), dict) else {}
    raw_price = str(offer.get("price", "")) if offer else ""
    raw_curr = offer.get("priceCurrency") if offer else "USD"
    price_cents, currency = parse_money(raw_price, raw_curr or "USD")

    # Fallback to HTML parsing if price missing in JSON-LD
    if price_cents is None:
        price_el = soup.select_one(".price, strong.price, .product-price")
        if price_el:
            price_cents, currency = parse_money(price_el.get_text(), currency or "USD")

    was = soup.find("s") or soup.find("del")
    compare, _ = parse_money(was.get_text(), currency) if was else (None, None)

    avail_str = str(offer.get("availability", "")) if offer else ""
    if "InStock" in avail_str:
        avail = "in_stock"
    elif "OutOfStock" in avail_str:
        avail = "out_of_stock"
    else:
        page_text = soup.get_text().lower()
        avail = "out_of_stock" if "out of stock" in page_text else "in_stock"

    name = data.get("name") if isinstance(data, dict) else None
    if not name and soup.h1:
        name = soup.h1.get_text(strip=True)

    return Observation(
        store=store,
        product_id=data.get("sku") if isinstance(data, dict) and data.get("sku") else _pid_from_url(url),
        url=url,
        name=name or "",
        price_cents=price_cents,
        currency=currency or "USD",
        compare_at_cents=compare,
        availability=avail,
    )


# --------------------------------------------------------------------------- Level 2: Maple & Co
@adapter("maple")
def extract_maple(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one(".product__title") or soup.select_one("h1")
    name = title_el.get_text(strip=True) if title_el else ""

    sale_el = soup.select_one(".price--sale")
    compare_el = soup.select_one(".price--compare")

    if sale_el:
        price_el = sale_el
    else:
        price_el = soup.select_one(".price:not(.price--compare)") or soup.select_one(".price")

    price_cents, currency = parse_money(price_el.get_text(" ", strip=True), "EUR") if price_el else (None, "EUR")
    compare, _ = parse_money(compare_el.get_text(" ", strip=True), currency) if compare_el else (None, None)

    if compare == price_cents:
        compare = None

    avail = "out_of_stock" if "Sold out" in soup.get_text() else "in_stock"
    return Observation(
        store=store,
        product_id=_pid_from_url(url),
        url=url,
        name=name,
        price_cents=price_cents,
        currency=currency or "EUR",
        compare_at_cents=compare,
        availability=avail,
    )


# --------------------------------------------------------------------------- Level 3: Zon
@adapter("zon")
def extract_zon(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    pid = _pid_from_url(url)

    if "Are you a human" in html or "robot check" in html.lower():
        return Observation(
            store=store, product_id=pid, url=url, name="", price_cents=None, currency="USD", notes=["robot check page"]
        )

    # If main box asks to select variant and we have variant links, fetch first variant page
    page_text_lower = soup.get_text().lower()
    if ("select a colour" in page_text_lower or "select a variant" in page_text_lower or "select an option" in page_text_lower or "select a color" in page_text_lower) and not urlparse(url).query:
        variant_a = soup.select_one("a[href*='variant=']")
        if variant_a and variant_a.get("href"):
            variant_url = urljoin(url, variant_a["href"])
            try:
                r_var = client.get(variant_url)
                if r_var.status_code == 200:
                    html = r_var.text
                    soup = BeautifulSoup(html, "html.parser")
            except Exception:
                pass

    # Dynamic title extraction (avoiding seed-specific class names)
    title_el = soup.find("h1") or soup.find("h2")
    if not title_el:
        for cand in soup.find_all(["span", "div"]):
            txt = cand.get_text(strip=True)
            if len(txt) > 10 and not cand.find_all(["span", "div"]):
                title_el = cand
                break

    full_title = title_el.get_text(strip=True) if title_el else ""

    # Dynamic pack size regex
    m_pack = re.search(r"(?:Pack of|\()?\s*(\d+)\s*(?:Pack|pack|count|ct|pcs|\))", full_title, re.IGNORECASE)
    if not m_pack:
        m_pack = re.search(r"Pack of (\d+)", full_title, re.IGNORECASE)
    pack = int(m_pack.group(1)) if m_pack else 1

    clean_name = re.sub(r"\s*\(?Pack of \d+\)?", "", full_title, flags=re.IGNORECASE).strip()

    # Isolate main offer container by decomposing "Other sellers" section
    main_soup = BeautifulSoup(str(soup), "html.parser")
    for el in main_soup.find_all(["div", "section", "h3", "h4"]):
        if "other sellers" in el.get_text().lower() and el.name in ("h3", "h4"):
            p = el.parent
            if p:
                p.decompose()
            break

    page_text_lower = main_soup.get_text().lower()
    avail = "out_of_stock" if ("out of stock" in page_text_lower or "currently unavailable" in page_text_lower) else "in_stock"

    price_cents: Optional[int] = None
    compare_at_cents: Optional[int] = None
    currency = "USD"

    if avail == "in_stock":
        # Compare-at / List price (inside <s>, <del>, or preceded by List Price:)
        for list_el in main_soup.find_all(["s", "del"]):
            c_val, _ = parse_money(list_el.get_text(), currency)
            if c_val:
                compare_at_cents = c_val
                list_el.decompose()

        for el in main_soup.find_all(string=re.compile(r"List Price:", re.I)):
            parent = el.parent
            if parent:
                c_val, _ = parse_money(parent.get_text(), currency)
                if c_val:
                    compare_at_cents = c_val
                    parent.decompose()

        # Look for explicit "Pack of X: $YYY.YY" pattern
        raw_text = main_soup.get_text(" ", strip=True)
        norm_text = re.sub(r"\$\s+", "$", raw_text)
        norm_text = re.sub(r"\s*\.\s*", ".", norm_text)

        pack_text_match = re.search(r"Pack of \d+:\s*\$\s*([\d,]+(?:\.\d{2})?)", norm_text, re.I)
        if pack_text_match:
            val, _ = parse_money(pack_text_match.group(1), currency)
            if val:
                price_cents = val

        if price_cents is None:
            # Extract price candidates from main offer container
            for el in main_soup.find_all(["div", "p", "span"]):
                txt = el.get_text(" ", strip=True)
                if "/ count" in txt or "/ unit" in txt or "/ item" in txt or "other sellers" in txt.lower():
                    continue
                txt_clean = re.sub(r"\$\s+", "$", txt)
                txt_clean = re.sub(r"\s*\.\s*", ".", txt_clean)
                m_p = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", txt_clean)
                if m_p:
                    val, _ = parse_money(m_p.group(1), currency)
                    if val and val != compare_at_cents:
                        price_cents = val
                        break

        # Fallback: Whole and fraction split elements without dollar symbol
        if price_cents is None:
            for container in main_soup.find_all(["div", "span"]):
                nums = [s.get_text(strip=True) for s in container.find_all(["span", "div"]) if s.get_text(strip=True).isdigit()]
                if len(nums) == 2 and len(nums[1]) in (1, 2):
                    try:
                        val = int(nums[0]) * 100 + int(nums[1].ljust(2, "0"))
                        if val != compare_at_cents:
                            price_cents = val
                            break
                    except ValueError:
                        pass

    return Observation(
        store=store,
        product_id=pid,
        url=url,
        name=clean_name or full_title,
        price_cents=price_cents,
        currency=currency,
        compare_at_cents=compare_at_cents,
        availability=avail,
        pack_size=pack,
        unit_price_cents=unit_price(price_cents, pack),
        notes=[] if price_cents is not None or avail == "out_of_stock" else ["no price found"],
    )


import hashlib

# --------------------------------------------------------------------------- Level 4: Shield Outfitters
@adapter("shield")
def extract_shield(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    pid = _pid_from_url(url)

    # 1. If html contains Shield challenge barrier, re-fetch via client (which solves challenge automatically)
    if "cf-c" in html or "Just a moment" in html:
        try:
            r = client.get(url)
            if r.status_code == 200:
                html = r.text
                soup = BeautifulSoup(html, "html.parser")
        except Exception:
            pass

    name: str = ""
    price_cents: Optional[int] = None
    currency: str = "GBP"
    compare: Optional[int] = None
    avail: str = "in_stock"

    # 2. Extract state from window.__STATE__ embedded script
    m_state = re.search(r"window\.__STATE__\s*=\s*(\{.*?\});", html)
    if m_state:
        try:
            state_data = json.loads(m_state.group(1))
            if isinstance(state_data, dict):
                # Product detail page: window.__STATE__ = {"product": {"id": "...", "title": "...", "offer": {...}}}
                if "product" in state_data and isinstance(state_data["product"], dict):
                    prod = state_data["product"]
                    name = str(prod.get("title") or "")
                    if prod.get("id"):
                        pid = str(prod["id"])
                    offer = prod.get("offer", {}) if isinstance(prod.get("offer"), dict) else {}
                    if "amount" in offer and offer["amount"] is not None:
                        price_cents = int(offer["amount"])
                    if offer.get("currency"):
                        currency = str(offer["currency"])
                    if offer.get("was") is not None:
                        try:
                            compare = int(offer["was"])
                        except (ValueError, TypeError):
                            compare = None
                    stock_val = offer.get("stock")
                    if stock_val in ("OUT_OF_STOCK", False, 0, "out_of_stock"):
                        avail = "out_of_stock"
                    else:
                        avail = "in_stock"

                # Multi-product catalog page: window.__STATE__ = {"prices": {"<pid>": {"amount": ...}}}
                elif "prices" in state_data and isinstance(state_data["prices"], dict):
                    prices_map = state_data["prices"]
                    if pid in prices_map and isinstance(prices_map[pid], dict):
                        item_info = prices_map[pid]
                        if "amount" in item_info and item_info["amount"] is not None:
                            price_cents = int(item_info["amount"])
                        if item_info.get("currency"):
                            currency = str(item_info["currency"])
        except json.JSONDecodeError:
            pass

    # 3. Fallback extraction if price_cents is still missing or name is placeholder
    if not name or name == "Loading…":
        # Try <h1 id="title"> or generic title selectors (ignoring "Loading…")
        title_el = soup.find("h1") or soup.select_one(".product-title, .item-title, .title")
        if title_el:
            t_txt = title_el.get_text(strip=True)
            if t_txt and t_txt != "Loading…":
                name = t_txt

        # Try page <title> (e.g. "Pilot & Co Tidal Wool Throw — Shield Outfitters")
        if not name or name == "Loading…":
            title_tag = soup.find("title")
            if title_tag:
                t_str = title_tag.get_text(strip=True)
                for delim in (" — ", " - ", " | "):
                    if delim in t_str:
                        cand = t_str.split(delim)[0].strip()
                        if cand and cand not in ("Just a moment…", "Loading…", "Shield Outfitters"):
                            name = cand
                            break
                if (not name or name == "Loading…") and t_str not in ("Just a moment…", "Loading…"):
                    name = t_str

    if price_cents is None:
        price_el = soup.select_one(".price, .current-price, .item-price, [data-price]")
        if price_el:
            raw_val = price_el.get("data-price") or price_el.get_text(" ", strip=True)
            if raw_val and raw_val != "Loading…":
                price_cents, currency = parse_money(str(raw_val), currency)

        if price_cents is None:
            m_price = re.search(r"£\s*(\d+(?:\.\d{2})?)", html)
            if m_price:
                price_cents, currency = parse_money(m_price.group(0), currency)

    if compare is None:
        compare_el = soup.find("s") or soup.find("del") or soup.select_one(".original-price, .was-price")
        if compare_el:
            c_txt = compare_el.get_text(strip=True)
            if c_txt and c_txt != "Loading…":
                compare, _ = parse_money(c_txt, currency)

    if compare == price_cents:
        compare = None

    notes: list[str] = []
    if price_cents is None:
        notes.append("shield extraction failed")

    return Observation(
        store=store,
        product_id=pid,
        url=url,
        name=name or pid,
        price_cents=price_cents,
        currency=currency or "GBP",
        compare_at_cents=compare,
        availability=avail,
        notes=notes,
        source="rules",
    )


# --------------------------------------------------------------------------- Level 5: Flux
@adapter("flux")
def extract_flux(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")

    # 1. Extract SKU from <div class="pdp" data-sku="..."> or fallback to URL
    sku = None
    pdp_div = soup.select_one(".pdp[data-sku]") or soup.find(attrs={"data-sku": True})
    if pdp_div:
        sku = pdp_div.get("data-sku")
    if not sku:
        sku = _pid_from_url(url)

    # 2. Extract build token from <meta name="flux-build" content="...">
    build_meta = soup.find("meta", attrs={"name": "flux-build"})
    build_val = build_meta.get("content") if build_meta else "v1.0"

    # 3. Compute GraphQL signature dynamically
    sig_prefix_meta = soup.find("meta", attrs={"name": re.compile(r"flux-(?:sig-prefix|prefix|sig|secret)", re.I)})
    sig_prefix = sig_prefix_meta.get("content") if (sig_prefix_meta and sig_prefix_meta.get("content")) else None
    if not sig_prefix:
        m_sig = re.search(r'\b(fx_[a-f0-9]{12,24})\b', html)
        sig_prefix = m_sig.group(1) if m_sig else "fx_1b11e1e8cfb25a950a27"
    sig_raw = f"{sig_prefix}|{sku}"
    sig = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:24]

    # 4. Issue GraphQL POST request
    graphql_url = urljoin(url, "/stores/flux/api/graphql")
    headers = {
        "Content-Type": "application/json",
        "x-flux-sig": sig,
        "x-flux-build": build_val,
    }
    payload = {
        "query": "query($sku:String!){product(sku:$sku){sku title offer{amount unit currency stock stale}}}",
        "variables": {"sku": sku},
    }

    product = {}
    offer = {}
    try:
        r = client.post(graphql_url, json=payload, headers=headers)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                product = data.get("data", {}).get("product", {}) or {}
                offer = product.get("offer", {}) or {}
    except Exception:
        pass

    # Extract fields from GraphQL offer response
    name = product.get("title") or ""
    if not name and soup.h1:
        name = soup.h1.get_text(strip=True)

    currency = offer.get("currency") or "USD"
    amount = offer.get("amount")
    unit = offer.get("unit")

    price_cents: Optional[int] = None
    if amount is not None:
        try:
            val_float = float(amount)
            if currency in ("JPY",):
                price_cents = int(round(val_float))
            elif unit == "major":
                price_cents = int(round(val_float * 100))
            else:
                # unit == "minor" or default
                price_cents = int(round(val_float))
        except (ValueError, TypeError):
            price_cents = None

    # Availability
    stock = offer.get("stock")
    if stock is False or stock == 0 or stock == "out_of_stock":
        avail = "out_of_stock"
    else:
        page_text = soup.get_text().lower()
        avail = "out_of_stock" if "out of stock" in page_text else "in_stock"

    # Stale price note
    notes: list[str] = []
    if offer.get("stale") is True:
        notes.append("stale price")

    # Fallback to embedded script tags if GraphQL failed
    if price_cents is None:
        scripts = soup.find_all("script")
        for s in scripts:
            if not s.string:
                continue
            txt = s.string.strip()
            if txt.startswith("{") and txt.endswith("}"):
                try:
                    d = json.loads(txt)
                    p_info = d.get("product") or d.get("item") or d
                    if "price" in p_info or "amount" in p_info:
                        raw_p = p_info.get("price") or p_info.get("amount")
                        if raw_p is not None:
                            price_cents = int(round(float(raw_p) * 100)) if isinstance(raw_p, float) else int(raw_p)
                        name = name or p_info.get("name") or p_info.get("title") or ""
                        break
                except Exception:
                    pass

    return Observation(
        store=store,
        product_id=sku,
        url=url,
        name=name or sku,
        price_cents=price_cents,
        currency=currency,
        availability=avail,
        notes=notes if notes else ([] if price_cents is not None else ["flux extraction failed"]),
    )



def extract(client: Client, store: str, adapter_name: str, url: str, html: str) -> Observation:
    fn = ADAPTERS.get(adapter_name)
    if fn is None:
        raise KeyError(f"no adapter named {adapter_name!r}")
    return fn(client, store, url, html)

