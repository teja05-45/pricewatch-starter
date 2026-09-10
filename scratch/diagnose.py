import hashlib
import json
from pathlib import Path

def main():
    labels_path = Path("eval/labels.json")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    cache_dir = Path("eval/out/.cache")
    
    # We need to map cache entries to snapshots
    provider_name = "groq"
    model_name = "openai/gpt-oss-120b"
    PROMPT_VERSION = "v4_candidate_validation"
    
    failures = []
    malformed_list = []
    
    for row in labels:
        snap_id = row["id"]
        store = row["store"]
        url = row["url"]
        exp = row["expected"]
        
        cache_key = hashlib.md5(f"{provider_name}_{model_name}_{PROMPT_VERSION}_{snap_id}_{url}".encode("utf-8")).hexdigest()
        cache_file = cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            print(f"Missing cache file for {snap_id}")
            continue
            
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if "error" in data:
            err_type = data["error"]
            if err_type == "malformed_output":
                malformed_list.append((snap_id, store, url, exp))
            failures.append({
                "id": snap_id,
                "store": store,
                "error": err_type,
                "expected": exp,
                "predicted": None
            })
            continue
            
        obs = data.get("obs", {})
        price_ok = (obs.get("price_cents") == exp.get("price_cents"))
        curr_ok = (obs.get("currency") == exp.get("currency"))
        avail_ok = (obs.get("availability") == exp.get("availability"))
        pack_ok = (obs.get("pack_size") == exp.get("pack_size", 1))
        
        if not (price_ok and curr_ok and avail_ok and pack_ok):
            failures.append({
                "id": snap_id,
                "store": store,
                "url": url,
                "expected": exp,
                "predicted": obs,
                "price_ok": price_ok,
                "curr_ok": curr_ok,
                "avail_ok": avail_ok,
                "pack_ok": pack_ok
            })
            
    print(f"Total failures/discrepancies: {len(failures)} out of {len(labels)}")
    print(f"Malformed output count: {len(malformed_list)}")
    print("\n--- DETAILED FAILURE BREAKDOWN ---")
    for f in failures:
        print(f"ID: {f['id']} | Store: {f['store']}")
        if "error" in f:
            print(f"  Error: {f['error']}")
        else:
            p_str = f"Price: {f['predicted'].get('price_cents')} vs Exp: {f['expected'].get('price_cents')} ({'OK' if f['price_ok'] else 'FAIL'})"
            c_str = f"Curr: {f['predicted'].get('currency')} vs Exp: {f['expected'].get('currency')} ({'OK' if f['curr_ok'] else 'FAIL'})"
            a_str = f"Avail: {f['predicted'].get('availability')} vs Exp: {f['expected'].get('availability')} ({'OK' if f['avail_ok'] else 'FAIL'})"
            pk_str = f"Pack: {f['predicted'].get('pack_size')} vs Exp: {f['expected'].get('pack_size', 1)} ({'OK' if f['pack_ok'] else 'FAIL'})"
            print(f"  {p_str} | {c_str} | {a_str} | {pk_str}")
        print("-" * 60)

if __name__ == "__main__":
    main()
