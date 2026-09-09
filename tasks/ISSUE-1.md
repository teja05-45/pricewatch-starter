# ISSUE-1 · False price-drop alerts (bug)

**Reported by:** ops · **Severity:** high · **Labels:** watcher, alerts

## What's happening

We keep getting "price dropped" alerts that aren't real. Since Monday we've had 40+ alerts
from Maple & Co and a handful from Zon, and when you open the product page the price hasn't
moved at all. A few of the alerts claim a 99% drop, which is obviously nonsense — a €937
notebook is not €1.07.

Corner Store alerts look fine, so it's not everything.

## What I think is going on

The watcher's diff logic is off. I had a look at `agents/watcher.py` and the percentage
calculation looks suspicious — I think it should divide by the previous price, not the
current one. That would explain the inflated percentages. Can someone fix the watcher and
add a test?

## How to reproduce

```bash
# terminal 1: the stores
cd ../pricewatch-stores && npm run dev

# terminal 2
pricewatch scan --stores-url http://localhost:4000 --store maple --out run1.jsonl
pricewatch scan --stores-url http://localhost:4000 --store maple --out run2.jsonl
pricewatch watch --history run1.jsonl --new run2.jsonl
```

Run the two scans a few times if the first pair is quiet — it's intermittent, which is part of
why nobody has fixed it yet. Compare `price_cents` in `run1.jsonl` with what the page actually shows.

`tests/test_extractor_maple.py` reproduces one of the symptoms and currently fails.

## Definition of done

- No alert fires when the price on the page hasn't changed, for every store that has an adapter.
- `price_cents` matches the price on the page (the pack price, default/selected variant) for Maple & Co.
- Existing tests stay green; the failing test passes; add tests for what you found.
- Note what the actual cause(s) were in `DECISION_LOG.md`, including whether the reporter's theory was right.
