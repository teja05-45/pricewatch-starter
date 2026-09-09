"""Eval harness for the LLM extractor (Stage 3 starting point).

Runs the LLM extractor over every snapshot in a directory, compares with labels.json, and
writes report.json. This skeleton measures one number and crashes on the first provider
error — improving it IS the exercise. The report schema the grader expects is documented
in tasks/ISSUE-3.md.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .agents.llm_extractor import extract_with_llm
from .providers import Provider


def run(provider: Provider, snapshots_dir: str | Path, labels_path: str | Path, out_dir: str | Path) -> dict:
    snapshots_dir, out_dir = Path(snapshots_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = {row["id"]: row for row in json.loads(Path(labels_path).read_text())}

    results = []
    t0 = time.time()
    for snap_id, row in labels.items():
        html = (snapshots_dir / row["file"]).read_text()
        obs = extract_with_llm(provider, row["store"], row["url"], html)
        exp = row["expected"]
        results.append({"id": snap_id, "price_ok": obs.price_cents == exp["price_cents"]})

    report = {
        "provider": provider.name,
        "n": len(results),
        "overall": {"price_exact": sum(r["price_ok"] for r in results) / max(1, len(results))},
        "elapsed_s": round(time.time() - t0, 2),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "label_issues.json").write_text("[]")
    return report
