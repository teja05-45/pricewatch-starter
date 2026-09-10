import os
import json
import hashlib
import time
import dotenv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

dotenv.load_dotenv()

from pricewatch.providers import load_provider, ProviderError, ProviderTimeout
from pricewatch.agents.llm_extractor import extract_with_llm

labels = json.loads(Path('eval/labels.json').read_text())
snapshots_dir = Path('eval/snapshots')
cache_dir = Path('eval/out/.cache')
cache_dir.mkdir(parents=True, exist_ok=True)

PROMPT_VERSION = 'v4_candidate_validation'

def process_row(row):
    provider = load_provider("groq")
    model_name = getattr(provider, 'model', 'default')
    snap_id = row['id']
    url = row['url']
    store = row['store']
    
    cache_key = hashlib.md5(f"{provider.name}_{model_name}_{PROMPT_VERSION}_{snap_id}_{url}".encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if "obs" in data or "error" in data:
                return snap_id, True, "cached"
        except Exception:
            pass
            
    file_path = snapshots_dir / row['file']
    if not file_path.exists():
        return snap_id, False, "missing_file"
        
    html = file_path.read_text(encoding='utf-8')
    start_time = time.time()
    
    obs = None
    err_type = None
    
    for attempt in range(4):
        try:
            obs = extract_with_llm(provider, store, url, html)
            err_type = None
            break
        except ProviderTimeout:
            err_type = "timeout"
            break
        except ProviderError as e:
            err_type = "provider_error"
            time.sleep(2.0 * (attempt + 1))
        except Exception:
            err_type = "provider_error"
            time.sleep(2.0 * (attempt + 1))
            
    lat = round((time.time() - start_time) * 1000, 1)
    if obs is not None:
        cache_file.write_text(json.dumps({"obs": obs.to_dict(), "latency_ms": lat}), encoding="utf-8")
        return snap_id, True, f"price={obs.price_cents}"
    else:
        cache_file.write_text(json.dumps({"error": err_type or "provider_error", "latency_ms": lat}), encoding="utf-8")
        return snap_id, False, err_type

print(f"Starting parallel cache population across {len(labels)} snapshots...")
t0 = time.time()

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(process_row, row): row['id'] for row in labels}
    completed = 0
    for future in as_completed(futures):
        snap_id = futures[future]
        completed += 1
        try:
            sid, ok, info = future.result()
            print(f"[{completed}/{len(labels)}] {sid}: ok={ok} ({info})")
        except Exception as e:
            print(f"[{completed}/{len(labels)}] {snap_id} ERROR: {e}")

print(f"Finished in {time.time() - t0:.2f}s!")
