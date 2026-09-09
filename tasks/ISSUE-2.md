# ISSUE-2 · "Below median" alert rule (feature)

**Requested by:** product · **Labels:** watcher, alerts

## Why

`drop_pct` only compares against the *previous* observation, so a store that yo-yos its price
every day (Flux does this) fires constantly, while a real, sustained bargain on a normally
stable item can slip through. We want a rule that compares against what the product
*usually* costs.

## Spec

Add a rule type `below_median` to `alerts.yaml`:

```yaml
rules:
  - type: below_median
    pct: 15          # fire when current <= median * (1 - pct/100)
    window_days: 30  # median is computed over observations in the trailing window
```

- The median is the median of **all observations of that product within the trailing
  `window_days`** (ending at, and excluding, the current observation).
- Products with fewer than 3 prior observations in the window do not fire.
- Observations with `price_cents == null` are ignored.
- Currency must match; if the product's currency changed inside the window, do not fire and
  add a note.
- Alert `rule` field: `"below_median"`. `previous_cents` carries the median (rounded to int).
- One alert per product per evaluation at most, even if both rules would fire — `below_median`
  wins over `drop_pct` when both match.

## Acceptance

```bash
pricewatch watch --history fixtures/history.jsonl --new fixtures/new.jsonl --rules alerts.yaml
```

emits exactly the alerts the rules imply. The autograder uses its own history fixtures with
prices spread over several weeks, including days with several observations and days with
none.

Implement it in a way you'd be happy to add a third rule to next week.
