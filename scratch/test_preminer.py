import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

def premine_html(html: str) -> dict:
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
            
    # 3. Text cleaning while preserving structural markers
    for tag in soup(["style", "svg", "iframe", "noscript"]):
        tag.decompose()
        
    full_text = soup.get_text(" ", strip=True)
    
    # 4. Action Buttons / CTAs & Availability signals
    in_stock_keywords = ["add to cart", "buy now", "in stock", "kjøp", "legg i handlekurv", "på lager", "tilgjengelig", "in den warenkorb"]
    out_of_stock_keywords = ["out of stock", "sold out", "currently unavailable", "utsolgt", "ikke på lager", "midlertidig utsolgt", "nicht auf lager"]
    
    found_in_stock = [kw for kw in in_stock_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text, re.IGNORECASE)]
    found_out_of_stock = [kw for kw in out_of_stock_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text, re.IGNORECASE)]
    
    # 5. Pack size signals
    pack_matches = re.findall(r"\b(\d+)\s*[-]?\s*(?:pack|pk|pakning|stk|pieces|items|count|set)\b|\b(?:pack|set|pakning|stk)\s*of\s*(\d+)\b", full_text, re.IGNORECASE)
    pack_candidates = []
    for m in pack_matches:
        num = m[0] or m[1]
        if num and 1 <= int(num) <= 100:
            pack_candidates.append(int(num))
            
    # 6. Price candidates with surrounding context
    price_pattern = re.compile(
        r"(?:(?:[₹$€£¥]\s*[\d\s.,]+)|(?:(?:kr|NOK|SEK|DKK|INR|USD|EUR|GBP|JPY|Rs\.?)\s*[\d\s.,]+)|(?:[\d\s.,]+\s*(?:kr|NOK|SEK|DKK|INR|USD|EUR|GBP|JPY|Rs\.?)))",
        re.IGNORECASE
    )
    
    candidates = []
    seen_vals = set()
    
    # Search all elements containing text
    for elem in soup.find_all(True):
        # Skip container elements if they have sub-elements to avoid duplicating child text
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
        "text_summary": full_text[:1000],
    }

labels = json.loads(Path('eval/labels.json').read_text())
print(f"Loaded {len(labels)} labels.")
for i in [0, 45, 52]: # Sample nk-000, bz-045, bz-052
    row = labels[i]
    p = Path('eval/snapshots') / row['file']
    res = premine_html(p.read_text(encoding='utf-8'))
    print(f"--- Snapshot {row['id']} ({row['store']}) ---")
    print("Expected:", row['expected'])
    print("Premined:", json.dumps(res, indent=2))
