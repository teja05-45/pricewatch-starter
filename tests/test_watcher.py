from pricewatch.agents.watcher import evaluate
from pricewatch.models import Observation


def obs(price, at, pid="P1", curr="USD"):
    return Observation(store="corner", product_id=pid, url="u", name="n", price_cents=price, currency=curr, observed_at=at)


def test_drop_fires():
    alerts = evaluate([obs(10000, "2026-09-01T00:00:00")], [obs(8000, "2026-09-02T00:00:00")], [{"type": "drop_pct", "pct": 10}])
    assert len(alerts) == 1 and alerts[0].rule == "drop_pct"


def test_no_history_no_alert():
    assert evaluate([], [obs(8000, "2026-09-02T00:00:00")], [{"type": "drop_pct", "pct": 10}]) == []


def test_increase_no_alert():
    assert evaluate([obs(8000, "2026-09-01T00:00:00")], [obs(10000, "2026-09-02T00:00:00")], [{"type": "drop_pct", "pct": 10}]) == []


def test_drop_pct_message_percentage():
    # Regression test for the alert copy — 10000 -> 8000 is 20.0% drop relative to 10000
    alerts = evaluate([obs(10000, "2026-09-01T00:00:00")], [obs(8000, "2026-09-02T00:00:00")], [{"type": "drop_pct", "pct": 10}])
    assert "20.0% drop" in alerts[0].message


def test_below_median_fires():
    history = [
        obs(10000, "2026-09-01T00:00:00"),
        obs(10000, "2026-09-02T00:00:00"),
        obs(10000, "2026-09-03T00:00:00"),
    ]
    # current = 8000 <= 10000 * 0.85 = 8500
    new = [obs(8000, "2026-09-04T00:00:00")]
    rules = [{"type": "below_median", "pct": 15, "window_days": 30}]
    alerts = evaluate(history, new, rules)
    assert len(alerts) == 1
    assert alerts[0].rule == "below_median"
    assert alerts[0].previous_cents == 10000
    assert alerts[0].current_cents == 8000


def test_below_median_requires_min_3_obs():
    history = [
        obs(10000, "2026-09-01T00:00:00"),
        obs(10000, "2026-09-02T00:00:00"),
    ]
    new = [obs(8000, "2026-09-04T00:00:00")]
    rules = [{"type": "below_median", "pct": 15, "window_days": 30}]
    alerts = evaluate(history, new, rules)
    assert len(alerts) == 0


def test_below_median_currency_mismatch():
    history = [
        obs(10000, "2026-09-01T00:00:00", curr="USD"),
        obs(10000, "2026-09-02T00:00:00", curr="EUR"),
        obs(10000, "2026-09-03T00:00:00", curr="USD"),
    ]
    new = [obs(8000, "2026-09-04T00:00:00", curr="USD")]
    rules = [{"type": "below_median", "pct": 15, "window_days": 30}]
    alerts = evaluate(history, new, rules)
    assert len(alerts) == 0


def test_below_median_priority_over_drop_pct():
    history = [
        obs(10000, "2026-09-01T00:00:00"),
        obs(10000, "2026-09-02T00:00:00"),
        obs(10000, "2026-09-03T00:00:00"),
    ]
    new = [obs(8000, "2026-09-04T00:00:00")]
    rules = [
        {"type": "drop_pct", "pct": 10},
        {"type": "below_median", "pct": 15, "window_days": 30},
    ]
    alerts = evaluate(history, new, rules)
    assert len(alerts) == 1
    assert alerts[0].rule == "below_median"

