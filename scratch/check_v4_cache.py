import os
import json
import hashlib
import dotenv
from pathlib import Path
from pricewatch.providers import load_provider
from pricewatch.models import Observation

dotenv.load_dotenv()
provider = load_provider("groq")

labels = json.loads(Path('eval/labels.json').read_text())
cache_dir = Path('eval/out/.cache')
model_name = getattr(provider, 'model', 'default')

results = []
missing = []

for row in labels:
    snap_id = row['id']
    url = row['url']
    exp = row['expected']
    cache_key = hashlib.md5(f"{provider.name}_{model_name}_v4_candidate_validation_{snap_id}_{url}".encode('utf-8')).hexdigest()
    cf = cache_dir / f"{cache_key}.json"
    if cf.exists():
        data = json.loads(cf.read_text())
        if "obs" in data:
            obs = Observation.from_dict(data["obs"])
            results.append({
                "id": snap_id,
                "store": row["store"],
                "price_ok": obs.price_cents == exp.get("price_cents"),
                "currency_ok": obs.currency == exp.get("currency"),
                "avail_ok": obs.availability == exp.get("availability"),
                "pack_ok": obs.pack_size == exp.get("pack_size", 1),
            })
        else:
            results.append({
                "id": snap_id,
                "store": row["store"],
                "price_ok": False,
                "currency_ok": False,
                "avail_ok": False,
                "pack_ok": False,
            })
    else:
        missing.append(snap_id)

print(f"Evaluated v4 cache entries for model={model_name}: {len(results)} / {len(labels)}, Missing: {len(missing)}")

if results:
    n = len(results)
    print("=== OVERALL METRICS ===")
    print("price_exact: ", round(sum(r["price_ok"] for r in results) / n, 4))
    print("currency:    ", round(sum(r["currency_ok"] for r in results) / n, 4))
    print("availability:", round(sum(r["avail_ok"] for r in results) / n, 4))
    print("pack_size:   ", round(sum(r["pack_ok"] for r in results) / n, 4))
