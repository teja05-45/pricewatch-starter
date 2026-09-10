import os
import json
from pathlib import Path
from pricewatch.providers import load_provider
from pricewatch.agents.llm_extractor import extract_with_llm

os.environ["GEMINI_MODEL"] = "gemini-3.6-flash"

try:
    provider = load_provider("gemini")
    print(f"Gemini provider initialized successfully with model {provider.model}.")
except Exception as e:
    print(f"Error loading Gemini provider: {e}")
    exit(1)

labels = json.loads(Path("eval/labels.json").read_text())[:5]
snapshots_dir = Path("eval/snapshots")

correct = 0
for row in labels:
    snap_id = row["id"]
    store = row["store"]
    url = row["url"]
    exp = row["expected"]
    html = (snapshots_dir / row["file"]).read_text(encoding="utf-8")
    
    obs = extract_with_llm(provider, store, url, html)
    is_ok = (obs.price_cents == exp['price_cents'] and obs.currency == exp['currency'] and obs.availability == exp['availability'] and obs.pack_size == exp.get('pack_size', 1))
    if is_ok:
        correct += 1
    print(f"[{snap_id}] OK: {is_ok} | Expected: price={exp['price_cents']}, curr={exp['currency']} | Extracted: price={obs.price_cents}, curr={obs.currency}, avail={obs.availability}, pack={obs.pack_size}")

print(f"\nGemini Smoke Test Result: {correct}/5 ({correct/5*100:.0f}%)")
