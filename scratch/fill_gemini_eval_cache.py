import os
import json
import hashlib
import time
from pathlib import Path
from pricewatch.providers import load_provider, ProviderError, ProviderTimeout
from pricewatch.agents.llm_extractor import extract_with_llm
from pricewatch.models import Observation

os.environ["GEMINI_MODEL"] = "gemini-2.5-flash"

labels = json.loads(Path('eval/labels.json').read_text())
snapshots_dir = Path('eval/snapshots')
cache_dir = Path('eval/out/.cache')
cache_dir.mkdir(parents=True, exist_ok=True)

try:
    provider = load_provider("gemini")
except Exception as e:
    print(f"Gemini provider load error: {e}")
    exit(1)

model_name = getattr(provider, 'model', 'default')
PROMPT_VERSION = 'v4_candidate_validation'

missing_rows = []
for row in labels:
    snap_id = row['id']
    url = row['url']
    cache_key = hashlib.md5(f"{provider.name}_{model_name}_{PROMPT_VERSION}_{snap_id}_{url}".encode('utf-8')).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    if not cache_file.exists():
        missing_rows.append((row, cache_file))

print(f"Provider: {provider.name} ({model_name}) | Total labels: {len(labels)}, missing in cache: {len(missing_rows)}")

for idx, (row, cache_file) in enumerate(missing_rows, 1):
    snap_id = row['id']
    store = row['store']
    url = row['url']
    file_path = snapshots_dir / row['file']
    if not file_path.exists():
        continue
    
    html = file_path.read_text(encoding='utf-8')
    start_time = time.time()
    
    print(f"[{idx}/{len(missing_rows)}] Gemini processing {snap_id} ({store})...")
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
            print(f"Gemini ProviderError attempt {attempt+1}: {e}")
            time.sleep(5 * (attempt + 1))
        except json.JSONDecodeError:
            err_type = "malformed_output"
            break
        except Exception as e:
            err_type = "provider_error"
            print(f"Gemini Exception attempt {attempt+1}: {e}")
            time.sleep(5 * (attempt + 1))
            
    lat = round((time.time() - start_time) * 1000, 1)
    if obs is not None:
        cache_file.write_text(json.dumps({"obs": obs.to_dict(), "latency_ms": lat}), encoding="utf-8")
        print(f"Gemini Success for {snap_id}: price_cents={obs.price_cents}")
    else:
        cache_file.write_text(json.dumps({"error": err_type or "provider_error", "latency_ms": lat}), encoding="utf-8")
        print(f"Gemini Failed for {snap_id}: error={err_type}")
        
    time.sleep(1.0)
