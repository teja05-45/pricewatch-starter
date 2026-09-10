import re
import sys
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from pricewatch.http import Client
from pricewatch.models import Observation
from pricewatch.agents.normalizer import parse_money, unit_price

sys.stdout.reconfigure(encoding='utf-8')

def extract_zon_improved(client: Client, store: str, url: str, html: str) -> Observation:
    soup = BeautifulSoup(html, "html.parser")
    pid = urlparse(url).path.rstrip("/").split("/")[-1]

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

    # Dynamic title extraction
    title_el = soup.find("h1") or soup.find("h2")
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

    # Availability
    page_text_lower = main_soup.get_text().lower()
    avail = "out_of_stock" if ("out of stock" in page_text_lower or "currently unavailable" in page_text_lower) else "in_stock"

    price_cents: int | None = None
    compare_at_cents: int | None = None
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

if __name__ == "__main__":
    client = Client()
    res = client.get("http://localhost:4000/stores/zon/")
    soup = BeautifulSoup(res.text, "html.parser")
    item_links = [a["href"] for a in soup.find_all("a") if "/item/" in a.get("href", "") or "/dp/" in a.get("href", "")]

    print(f"Testing improved extract_zon on {len(item_links)} items:")
    for link in item_links:
        full_url = "http://localhost:4000" + link
        r = client.get(full_url)
        obs = extract_zon_improved(client, "zon", full_url, r.text)
        print(f"URL: {link} -> Name: '{obs.name}', Price: {obs.price_cents}, Compare: {obs.compare_at_cents}, Pack: {obs.pack_size}, Avail: {obs.availability}")
