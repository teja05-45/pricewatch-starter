import os
import json
import hashlib
import time
import dotenv
from pathlib import Path

dotenv.load_dotenv()

from pricewatch.providers import load_provider, ProviderError, ProviderTimeout
from pricewatch.agents.llm_extractor import extract_with_llm

provider = load_provider("groq")

labels = json.loads(Path('eval/labels.json').read_text())
snapshots_dir = Path('eval/snapshots')
cache_dir = Path('eval/out/.cache')
cache_dir.mkdir(parents=True, exist_ok=True)

PROMPT_VERSION = 'v4_candidate_validation'
model_name = getattr(provider, 'model', 'default')

print(f"Populating cache for provider={provider.name}, model={model_name}, version={PROMPT_VERSION}...")

successes = 0
for idx, row in enumerate(labels, 1):
    snap_id = row['id']
    url = row['url']
    store = row['store']
    
    cache_key = hashlib.md5(f"{provider.name}_{model_name}_{PROMPT_VERSION}_{snap_id}_{url}".encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if "obs" in data:
                successes += 1
                continue
        except Exception:
            pass
            
    file_path = snapshots_dir / row['file']
    if not file_path.exists():
        continue
        
    html = file_path.read_text(encoding='utf-8')
    start_time = time.time()
    
    obs = None
    err_type = None
    
    for attempt in range(5):
        try:
            obs = extract_with_llm(provider, store, url, html)
            err_type = None
            break
        except ProviderTimeout:
            err_type = "timeout"
            break
        except ProviderError as e:
            err_type = "provider_error"
            print(f"[{idx}/{len(labels)}] ProviderError {snap_id} attempt {attempt+1}: {e}")
            time.sleep(3.0 * (attempt + 1))
        except Exception as e:
            err_type = "provider_error"
            print(f"[{idx}/{len(labels)}] Exception {snap_id} attempt {attempt+1}: {e}")
            time.sleep(3.0 * (attempt + 1))
            
    lat = round((time.time() - start_time) * 1000, 1)
    if obs is not None:
        cache_file.write_text(json.dumps({"obs": obs.to_dict(), "latency_ms": lat}), encoding="utf-8")
        successes += 1
        print(f"[{idx}/{len(labels)}] {snap_id} SUCCESS -> price_cents={obs.price_cents}")
    else:
        cache_file.write_text(json.dumps({"error": err_type or "provider_error", "latency_ms": lat}), encoding="utf-8")
        print(f"[{idx}/{len(labels)}] {snap_id} FAILED -> error={err_type}")
        
    time.sleep(0.5)

print(f"\nDone! Successfully populated {successes} / {len(labels)} cache entries.")
