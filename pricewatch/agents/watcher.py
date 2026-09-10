"""Watcher agent: compares new observations against history and raises alerts.

History is a list of observations ordered by `observed_at`. Rules come from alerts.yaml.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import statistics
from typing import Iterable

from ..models import Alert, Observation


def _key(o: Observation) -> tuple[str, str]:
    return (o.store, o.product_id)


def _by_product(history: Iterable[Observation]) -> dict[tuple[str, str], list[Observation]]:
    out: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for o in history:
        out[_key(o)].append(o)
    for v in out.values():
        v.sort(key=lambda o: o.observed_at)
    return out


def _parse_dt(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def rule_drop_pct(prev: Observation, cur: Observation, pct: float) -> Alert | None:
    if prev.price_cents is None or cur.price_cents is None:
        return None
    if prev.currency != cur.currency:
        return None
    if prev.price_cents <= 0 or cur.price_cents >= prev.price_cents:
        return None

    drop = (prev.price_cents - cur.price_cents) / prev.price_cents * 100
    if drop >= pct:
        return Alert(
            store=cur.store,
            product_id=cur.product_id,
            rule="drop_pct",
            message=f"{cur.name or cur.product_id}: {prev.price_cents} -> {cur.price_cents} ({drop:.1f}% drop)",
            previous_cents=prev.price_cents,
            current_cents=cur.price_cents,
            observed_at=cur.observed_at,
        )
    return None


def rule_below_median(prior: list[Observation], cur: Observation, pct: float, window_days: int) -> Alert | None:
    if cur.price_cents is None:
        return None

    cur_dt = _parse_dt(cur.observed_at)
    valid_in_window: list[Observation] = []

    for o in prior:
        if o.price_cents is None:
            continue
        o_dt = _parse_dt(o.observed_at)
        delta_days = (cur_dt - o_dt).total_seconds() / 86400.0
        if 0 < delta_days <= window_days:
            valid_in_window.append(o)

    if not valid_in_window:
        return None

    # Currency consistency check
    if any(o.currency != cur.currency for o in valid_in_window):
        return None

    # Group by calendar date (daily closing prices: last observation on each day)
    by_day: dict[str, int] = {}
    for o in valid_in_window:
        day_str = o.observed_at[:10]
        by_day[day_str] = o.price_cents  # last observation overwrites earlier ones for the day

    closing_prices = list(by_day.values())
    if len(closing_prices) < 3:
        return None

    med = statistics.median(closing_prices)
    threshold = med * (1.0 - pct / 100.0)

    if cur.price_cents <= threshold:
        med_cents = int(round(med))
        return Alert(
            store=cur.store,
            product_id=cur.product_id,
            rule="below_median",
            message=f"{cur.name or cur.product_id}: price {cur.price_cents} is below median {med_cents}",
            previous_cents=med_cents,
            current_cents=cur.price_cents,
            observed_at=cur.observed_at,
        )

    return None


def evaluate(history: list[Observation], new: list[Observation], rules: list[dict]) -> list[Alert]:
    """Evaluate `rules` for each observation in `new` against `history` (which must not include `new`)."""
    alerts: list[Alert] = []
    hist = _by_product(history)

    for cur in sorted(new, key=lambda o: o.observed_at):
        prior = hist.get(_key(cur), [])
        prev = prior[-1] if prior else None

        triggered: dict[str, Alert] = {}

        for rule in rules:
            rule_type = rule.get("type")
            if rule_type == "drop_pct" and prev is not None:
                a = rule_drop_pct(prev, cur, float(rule.get("pct", 10)))
                if a:
                    triggered["drop_pct"] = a
            elif rule_type == "below_median":
                a = rule_below_median(prior, cur, float(rule.get("pct", 15)), int(rule.get("window_days", 30)))
                if a:
                    triggered["below_median"] = a

        # Priority resolution: below_median wins over drop_pct
        if "below_median" in triggered:
            alerts.append(triggered["below_median"])
        elif "drop_pct" in triggered:
            alerts.append(triggered["drop_pct"])

        hist[_key(cur)] = prior + [cur]

    return alerts

