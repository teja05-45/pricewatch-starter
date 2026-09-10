import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

labels = json.loads(Path("eval/labels.json").read_text(encoding="utf-8"))
bz52 = [r for r in labels if r["id"] == "bz-052"]
print("BZ-052 LABEL:", bz52)

snap_path = Path("eval/snapshots/bz-052.html")
if snap_path.exists():
    print("BZ-052 HTML:\n", snap_path.read_text(encoding="utf-8"))
