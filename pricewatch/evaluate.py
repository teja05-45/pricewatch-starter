"""Eval harness for the LLM extractor (Stage 3).

Runs the LLM extractor over every snapshot in a directory, compares with labels.json, and
writes report.json, label_issues.json, and error_analysis.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from .agents.llm_extractor import extract_with_llm
from .models import Observation
from .providers import Provider, ProviderError, ProviderTimeout


def run(provider: Provider, snapshots_dir: str | Path, labels_path: str | Path, out_dir: str | Path) -> dict:
    snapshots_dir, out_dir = Path(snapshots_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    labels = json.loads(Path(labels_path).read_text())
    
    results = []
    error_analysis = []
    errors = {"timeout": 0, "malformed_output": 0, "provider_error": 0}
    latencies_ms = []

    total_input_tokens = 0
    total_output_tokens = 0

    t0 = time.time()

    # Real baseline evaluation using rule-based extractors
    from .agents import extractor
    from .http import Client
    dummy_client = Client()
    baseline_correct = 0

    for row in labels:
        snap_id = row["id"]
        store = row["store"]
        url = row["url"]
        exp = row["expected"]
        file_path = snapshots_dir / row["file"]

        if not file_path.exists():
            continue

        html = file_path.read_text(encoding="utf-8")
        
        total_input_tokens += len(html) // 4
        total_output_tokens += 50

        if store in extractor.ADAPTERS:
            try:
                b_obs = extractor.extract(dummy_client, store, store, url, html)
                if b_obs and b_obs.price_cents == exp.get("price_cents"):
                    baseline_correct += 1
            except Exception:
                pass

        model_name = getattr(provider, "model", "default")
        PROMPT_VERSION = "v4_candidate_validation"
        cache_key = hashlib.md5(f"{provider.name}_{model_name}_{PROMPT_VERSION}_{snap_id}_{url}".encode("utf-8")).hexdigest()
        cache_file = cache_dir / f"{cache_key}.json"

        start_time = time.time()
        obs: Observation | None = None
        err_type = None

        if cache_file.exists():
            try:
                cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                if "error" in cached_data:
                    err_type = cached_data["error"]
                    errors[err_type] = errors.get(err_type, 0) + 1
                else:
                    obs = Observation.from_dict(cached_data["obs"])
                lat = cached_data.get("latency_ms", 100.0)
            except Exception:
                cache_file.unlink(missing_ok=True)

        if obs is None and err_type is None:
            try:
                obs = extract_with_llm(provider, store, url, html)
                cache_file.write_text(json.dumps({"obs": obs.to_dict(), "latency_ms": round((time.time() - start_time) * 1000, 1)}), encoding="utf-8")
                lat = (time.time() - start_time) * 1000.0
            except ProviderTimeout:
                err_type = "timeout"
                errors["timeout"] += 1
                cache_file.write_text(json.dumps({"error": "timeout"}), encoding="utf-8")
                lat = (time.time() - start_time) * 1000.0
            except ProviderError:
                err_type = "provider_error"
                errors["provider_error"] += 1
                cache_file.write_text(json.dumps({"error": "provider_error"}), encoding="utf-8")
                lat = (time.time() - start_time) * 1000.0
            except json.JSONDecodeError:
                err_type = "malformed_output"
                errors["malformed_output"] += 1
                cache_file.write_text(json.dumps({"error": "malformed_output"}), encoding="utf-8")
                lat = (time.time() - start_time) * 1000.0
            except Exception:
                err_type = "provider_error"
                errors["provider_error"] += 1
                cache_file.write_text(json.dumps({"error": "provider_error"}), encoding="utf-8")
                lat = (time.time() - start_time) * 1000.0

        latencies_ms.append(lat)

        if obs is not None and err_type is None:
            price_ok = (obs.price_cents == exp.get("price_cents"))
            currency_ok = (obs.currency == exp.get("currency"))
            avail_ok = (obs.availability == exp.get("availability"))
            pack_ok = (obs.pack_size == exp.get("pack_size", 1))
        else:
            price_ok = False
            currency_ok = False
            avail_ok = False
            pack_ok = False

        results.append({
            "id": snap_id,
            "store": store,
            "price_ok": price_ok,
            "currency_ok": currency_ok,
            "avail_ok": avail_ok,
            "pack_ok": pack_ok,
        })

        if not (price_ok and currency_ok and avail_ok and pack_ok):
            reasons = []
            if not price_ok:
                reasons.append("wrong_price")
            if not currency_ok:
                reasons.append("wrong_currency")
            if not avail_ok:
                reasons.append("wrong_availability")
            if not pack_ok:
                reasons.append("wrong_pack_size")
            if err_type:
                reasons.append(err_type)
                
            error_analysis.append({
                "snapshot": snap_id,
                "store": store,
                "expected": exp,
                "predicted": obs.to_dict() if obs else None,
                "error_types": reasons,
            })

    n = len(results) or 1
    overall = {
        "price_exact": round(sum(r["price_ok"] for r in results) / n, 2),
        "currency": round(sum(r["currency_ok"] for r in results) / n, 2),
        "availability": round(sum(r["avail_ok"] for r in results) / n, 2),
        "pack_size": round(sum(r["pack_ok"] for r in results) / n, 2),
    }

    per_store = {}
    stores = sorted(list(set(r["store"] for r in results)))
    for s in stores:
        sub = [r for r in results if r["store"] == s]
        sn = len(sub) or 1
        per_store[s] = {
            "n": len(sub),
            "price_exact": round(sum(r["price_ok"] for r in sub) / sn, 2),
            "currency": round(sum(r["currency_ok"] for r in sub) / sn, 2),
            "availability": round(sum(r["avail_ok"] for r in sub) / sn, 2),
            "pack_size": round(sum(r["pack_ok"] for r in sub) / sn, 2),
        }

    sorted_lats = sorted(latencies_ms) if latencies_ms else [0.0]
    p50_idx = int(math.ceil(0.50 * len(sorted_lats))) - 1
    p95_idx = int(math.ceil(0.95 * len(sorted_lats))) - 1

    usd_estimate = round(total_input_tokens * (0.15 / 1_000_000) + total_output_tokens * (0.60 / 1_000_000), 4)

    report = {
        "provider": provider.name,
        "model": getattr(provider, "model", "default"),
        "n": len(results),
        "overall": overall,
        "per_store": per_store,
        "errors": errors,
        "cost": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "usd_estimate": usd_estimate,
        },
        "latency_ms": {
            "p50": round(sorted_lats[max(0, p50_idx)], 1),
            "p95": round(sorted_lats[max(0, p95_idx)], 1),
        },
        "baseline": {"price_exact": round(baseline_correct / n, 2)},
        "elapsed_s": round(time.time() - t0, 2),
    }

    # Generic label issue detection (detecting label anomalies against HTML evidence)
    label_issues = []
    from bs4 import BeautifulSoup
    from .agents.normalizer import parse_money

    for row in labels:
        snap_id = row.get("id")
        exp_cents = row.get("expected", {}).get("price_cents")
        file_path = snapshots_dir / row.get("file", "")

        if not snap_id or not file_path.exists() or exp_cents is None:
            continue

        try:
            html = file_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "html.parser")
            reason = None

            exp_dollars = exp_cents / 100.0
            exp_int = int(exp_dollars) if exp_dollars.is_integer() else exp_dollars

            # 1. EMI / Monthly check
            for el in soup.find_all(["div", "p", "span", "b", "strong", "li"]):
                txt = el.get_text(" ", strip=True)
                if any(kw in txt.lower() for kw in ["emi", "per month", "/month", "/mo", "monthly", "installment"]):
                    val_cents, _ = parse_money(txt)
                    if val_cents == exp_cents or str(exp_int) in txt:
                        reason = "label uses the EMI monthly amount, not the price"
                        break

            # 2. List / struck-through price check
            if not reason:
                for s_tag in soup.find_all(["s", "del"]):
                    txt = s_tag.get_text()
                    val_cents, _ = parse_money(txt)
                    if val_cents == exp_cents or str(exp_int) in txt:
                        reason = "label uses original/list price instead of sale price"
                        break

            # 3. Discount check
            if not reason:
                for el in soup.find_all(["div", "p", "span"]):
                    txt = el.get_text(" ", strip=True)
                    if any(kw in txt.lower() for kw in ["save", "discount", "off"]):
                        val_cents, _ = parse_money(txt)
                        if val_cents == exp_cents:
                            reason = "label uses discount amount instead of selling price"
                            break

            if reason:
                label_issues.append({"id": snap_id, "reason": reason})
        except Exception:
            pass

    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "label_issues.json").write_text(json.dumps(label_issues, indent=2), encoding="utf-8")
    (out_dir / "error_analysis.json").write_text(json.dumps(error_analysis, indent=2), encoding="utf-8")

    return report
