import sys
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from pricewatch.agents.normalizer import parse_money

sys.stdout.reconfigure(encoding='utf-8')

labels_path = Path("eval/labels.json")
snapshots_dir = Path("eval/snapshots")
labels = json.loads(labels_path.read_text(encoding="utf-8"))

def detect_label_issues(labels, snapshots_dir):
    label_issues = []
    
    for row in labels:
        snap_id = row["id"]
        exp_cents = row["expected"].get("price_cents")
        file_path = snapshots_dir / row["file"]
        
        if not file_path.exists() or exp_cents is None:
            continue
            
        html = file_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")

        reason = None
        
        # Check 1: Does exp_cents match an EMI text node?
        # Search for all text nodes containing numbers
        exp_dollars = exp_cents / 100.0
        exp_int = int(exp_dollars) if exp_dollars.is_integer() else exp_dollars
        
        for el in soup.find_all(["div", "p", "span", "b", "strong", "li"]):
            txt = el.get_text(" ", strip=True)

            # Check if this node mentions EMI / monthly
            is_emi_node = any(kw in txt.lower() for kw in ["emi", "per month", "/month", "/mo", "monthly", "installment"])
            if is_emi_node:
                # Does this EMI node contain exp_cents value?
                val_cents, _ = parse_money(txt)
                if val_cents == exp_cents or str(exp_int) in txt:
                    reason = "label uses the EMI monthly amount, not the price"
                    break

        # Check 2: Does exp_cents match a struck-through / list price node?
        if not reason:
            for s_tag in soup.find_all(["s", "del"]):
                txt = s_tag.get_text()
                val_cents, _ = parse_money(txt)
                if val_cents == exp_cents or str(exp_int) in txt:
                    reason = "label uses original/list price instead of sale price"
                    break

        # Check 3: Does exp_cents match a discount / savings node?
        if not reason:
            for el in soup.find_all(["div", "p", "span"]):
                txt = el.get_text(" ", strip=True)
                if any(kw in txt.lower() for kw in ["save", "discount", "off"]):
                    val_cents, _ = parse_money(txt)
                    if val_cents == exp_cents:
                        reason = "label uses discount amount instead of selling price"
                        break

        if reason:
            label_issues.append({"id": snap_id, "reason": reason})

    return label_issues

found = detect_label_issues(labels, snapshots_dir)
print(f"Detected {len(found)} label issues:")
print(json.dumps(found, indent=2))
