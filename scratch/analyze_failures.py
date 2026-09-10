import json
import hashlib
from pathlib import Path
from pricewatch.models import Observation

labels = json.loads(Path('eval/labels.json').read_text())
cache_dir = Path('eval/out/.cache')

print(f"Total Labels: {len(labels)}")

wrong_snapshots = []
failures_by_category = {
    "price": [],
    "currency": [],
    "availability": [],
    "pack_size": [],
    "malformed_json": []
}

# We test with the cached results for v3/v4 to see exact failures
for row in labels:
    snap_id = row['id']
    url = row['url']
    store = row['store']
    exp = row['expected']
    
    # Check v3 or v4 cache file
    v3_key = hashlib.md5(f"groq_openai/gpt-oss-120b_v3_semantic_rules_{snap_id}_{url}".encode('utf-8')).hexdigest()
    v4_key = hashlib.md5(f"groq_openai/gpt-oss-120b_v4_candidate_validation_{snap_id}_{url}".encode('utf-8')).hexdigest()
    
    cf = cache_dir / f"{v4_key}.json"
    if not cf.exists():
        cf = cache_dir / f"{v3_key}.json"
        
    obs = None
    err = None
    if cf.exists():
        data = json.loads(cf.read_text())
        if "obs" in data:
            obs = Observation.from_dict(data["obs"])
        elif "error" in data:
            err = data["error"]
            
    if obs is None:
        wrong_snapshots.append({
            "id": snap_id,
            "store": store,
            "expected": exp,
            "predicted": f"ERROR: {err or 'Missing'}",
            "mismatches": ["malformed_json"]
        })
        failures_by_category["malformed_json"].append(snap_id)
        continue
        
    mismatches = []
    if obs.price_cents != exp.get("price_cents"):
        mismatches.append("price")
        failures_by_category["price"].append(snap_id)
    if obs.currency != exp.get("currency"):
        mismatches.append("currency")
        failures_by_category["currency"].append(snap_id)
    if obs.availability != exp.get("availability"):
        mismatches.append("availability")
        failures_by_category["availability"].append(snap_id)
    if obs.pack_size != exp.get("pack_size", 1):
        mismatches.append("pack_size")
        failures_by_category["pack_size"].append(snap_id)
        
    if mismatches:
        wrong_snapshots.append({
            "id": snap_id,
            "store": store,
            "expected": exp,
            "predicted": {
                "price_cents": obs.price_cents,
                "currency": obs.currency,
                "availability": obs.availability,
                "pack_size": obs.pack_size,
            },
            "mismatches": mismatches
        })

print(f"Total wrong snapshots: {len(wrong_snapshots)}")
print("\nFailures summary by category:")
for cat, ids in failures_by_category.items():
    print(f"- {cat}: {len(ids)} ({ids[:10]}...)")

out_analysis = {
    "total": len(labels),
    "wrong_count": len(wrong_snapshots),
    "by_category": {cat: len(ids) for cat, ids in failures_by_category.items()},
    "wrong_details": wrong_snapshots
}

Path("scratch/failure_analysis.json").write_text(json.dumps(out_analysis, indent=2), encoding="utf-8")
