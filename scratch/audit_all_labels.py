import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

labels_path = Path("eval/labels.json")
snapshots_dir = Path("eval/snapshots")

labels = json.loads(labels_path.read_text(encoding="utf-8"))

print(f"Total labeled snapshots: {len(labels)}")

label_issues_found = []

for row in labels:
    snap_id = row["id"]
    exp_cents = row["expected"].get("price_cents")
    file_path = snapshots_dir / row["file"]
    
    if not file_path.exists() or exp_cents is None:
        continue
        
    html = file_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    
    dollars_val = exp_cents / 100.0
    dollar_str = f"{dollars_val:.2f}"
    dollar_str_int = f"{int(dollars_val)}" if dollars_val.is_integer() else dollar_str
    
    # Context check: find all text blocks containing dollar_str or dollar_str_int
    issue_type = None
    
    # 1. EMI / Monthly check
    emi_pats = [
        rf"\${dollar_str}\s*/\s*mo",
        rf"\${dollar_str_int}\s*/\s*mo",
        rf"\${dollar_str}\s*per\s*month",
        rf"\${dollar_str_int}\s*per\s*month",
        rf"emi\s*:\s*\${dollar_str}",
        rf"emi\s*:\s*\${dollar_str_int}",
        rf"month\s*for\s*\${dollar_str}",
    ]
    for p in emi_pats:
        if re.search(p, html, re.IGNORECASE):
            issue_type = "label uses the EMI monthly amount, not the price"
            break
            
    # 2. List price / struck-through price check
    if not issue_type:
        for s_tag in soup.find_all(["s", "del"]):
            stxt = s_tag.get_text()
            if dollar_str in stxt or (dollars_val.is_integer() and str(int(dollars_val)) in stxt):
                issue_type = "label uses original/list price instead of sale price"
                break

    # 3. Discount check
    if not issue_type:
        for p in [rf"save\s*\${dollar_str}", rf"discount\s*:\s*\${dollar_str}"]:
            if re.search(p, html, re.IGNORECASE):
                issue_type = "label uses discount amount instead of price"
                break
                
    if issue_type:
        label_issues_found.append({"id": snap_id, "reason": issue_type})

print(f"\nFound {len(label_issues_found)} label issues out of {len(labels)}:")
print(json.dumps(label_issues_found, indent=2))
