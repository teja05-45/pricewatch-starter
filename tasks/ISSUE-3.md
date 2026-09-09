# ISSUE-3 · LLM extraction for stores we've never seen — and proof that it works

**Requested by:** product · **Labels:** llm, eval

## Why

Every new store today means writing an adapter. We want the swarm to fall back to an
LLM-based extractor for unknown stores. But an extractor we can't measure is a liability:
before it goes near production we need an eval that tells us, per store, how often it's
right, what it costs, and how it fails.

## Part A — the extractor

`pricewatch extract --url URL --html FILE --llm --provider NAME` must return an Observation
built by a model. Start from `agents/llm_extractor.py`. Use your own API key with any
provider (`openai` and `anthropic` are wired; add another if you like). Keep the provider
interface in `providers/__init__.py` intact — the autograder injects its own provider through
`PRICEWATCH_PROVIDER_PATH`, and it keys its answers on `metadata["source_url"]`.

## Part B — the eval (this is what we grade)

`eval/snapshots/` holds 90 saved product pages from two stores you have no adapter for
(Nordkart, a Norwegian electronics shop, and Bazaario, an Indian marketplace).
`eval/labels.json` holds what we believe each page says.

```bash
pricewatch eval --snapshots eval/snapshots --labels eval/labels.json --provider openai --out eval/out
```

must write two files:

### `eval/out/report.json`

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "n": 90,
  "overall":   {"price_exact": 0.83, "currency": 0.98, "availability": 0.90, "pack_size": 0.92},
  "per_store": {"nordkart": {"n": 45, "price_exact": 0.80, "currency": 1.0, "availability": 0.9, "pack_size": 0.93},
                "bazaario": {"n": 45, "price_exact": 0.87, "currency": 0.97, "availability": 0.9, "pack_size": 0.9}},
  "errors":    {"timeout": 1, "malformed_output": 2, "provider_error": 0},
  "cost":      {"input_tokens": 180000, "output_tokens": 4200, "usd_estimate": 0.03},
  "latency_ms": {"p50": 900, "p95": 2100},
  "baseline":  {"price_exact": 0.0}
}
```

Rules: a snapshot that hit an error counts as **wrong** in the accuracy numbers, not
skipped, and is counted in `errors`. `n` is the number of snapshots attempted. `baseline` is
the rule-based extractor (`--llm` off) on the same snapshots — for stores it has no adapter
for, that's 0, which is the point. Extra keys are fine; missing keys are not.

### `eval/out/label_issues.json`

The labels were written by a person in a hurry. Some are wrong — not always obviously. A few are arguable. List the
snapshot ids you believe are mislabeled, with one line each on why:

```json
[{"id": "bz-014", "reason": "label uses the EMI monthly amount, not the price"}]
```

You are graded on precision and recall against our answer key. Listing every id scores zero.

## Part C — the part you can't iterate against

The autograder also runs **your** LLM extractor — `pricewatch extract --llm --provider anthropic`,
with **our** Anthropic API key in the standard `ANTHROPIC_API_KEY` env var — on 40 product pages from two stores that appear nowhere in this repo,
in languages and formats you haven't seen, and scores the Observations it prints against our
truth: price 60%, currency 20%, availability 20%. This is 8 of Stage 3's 20 points, and it is the
only part of the assignment that measures how good your *model-facing* engineering is — prompt,
page cleaning, output parsing, unit handling — on a distribution you didn't tune for. Write the
extractor for the real internet, not for Nordkart and Bazaario. Think about currencies without
minor units, pages in languages you don't read, and what a "price" is when several numbers are
bold. Develop with whatever provider and key you like, but the `anthropic` provider path must work
with nothing but `ANTHROPIC_API_KEY` set (we set `PRICEWATCH_MODEL` too); don't hard-code a model
name that won't exist.

## Constraints

- The harness must not crash on a provider timeout or on output that isn't valid JSON.
  The autograder's provider will do both to you.
- The harness must be re-runnable without re-spending: cache provider responses on disk,
  keyed by something sensible.
- Commit your real-key run's `eval/out/` so we can read it. The autograder re-runs the harness
  with a fault-injecting provider (structure and error handling), then runs your extractor with a
  real model on the hidden pages (Part C).

## Definition of done

Both files written in the schema above; harness survives faults; `label_issues.json`
reflects what you actually found; a paragraph in `DECISION_LOG.md` on what the model got
wrong and what you'd change with another day.
