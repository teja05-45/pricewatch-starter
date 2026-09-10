import os
import json
import hashlib
import time
from pathlib import Path
from pricewatch.evaluate import run
from pricewatch.providers import load_provider

os.environ["GROQ_MODEL"] = "openai/gpt-oss-120b"
provider = load_provider("groq")

out_dir = Path("eval/out")
report = run(provider, "eval/snapshots", "eval/labels.json", out_dir)

print("=== FINAL EVALUATION REPORT ===")
print(json.dumps(report, indent=2))

error_analysis_file = out_dir / "error_analysis.json"
if error_analysis_file.exists():
    errors = json.loads(error_analysis_file.read_text())
    print(f"\nTotal Discrepancies: {len(errors)}")
    for err in errors[:10]:
        print(f"- [{err['snapshot']}] ({err['store']}) Expected: {err['expected']['price_cents']}, Pred: {err['predicted'].get('price_cents') if err['predicted'] else 'None'} | Types: {err['error_types']}")
