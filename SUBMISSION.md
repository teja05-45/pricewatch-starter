# Submitting your work

## Checklist before your first submission

- [ ] `pytest` passes locally (all of it, including the test that failed at the start).
- [ ] `pricewatch scan --stores-url http://localhost:4000 --out obs.jsonl` runs to completion
      without a traceback, against a stores instance started with a seed you invented:
      `docker run --rm -p 4000:4000 -e STORE_SEED=mytest ghcr.io/i95dev/pricewatch-stores:latest`.
      Compare `obs.jsonl` against `curl "http://localhost:4000/grader-truth?key=dev-truth-key"` for
      levels 1–2, and against what a browser shows you for levels 3–5 (there is no oracle for those).
- [ ] `pricewatch watch --history <file> --new <file>` runs with your `alerts.yaml`.
- [ ] `pricewatch eval --provider echo --out eval/out` runs without a key and writes both files.
- [ ] `eval/out/` from your real-key run is committed.
- [ ] `DECISION_LOG.md` frontmatter is filled in — especially `median_basis` and `levels_attempted`.
- [ ] `pip install -e .` works from a clean clone. If you added dependencies, they're in `pyproject.toml`.
      (TypeScript port: `npm ci && npm run build` must work, and `npx pricewatch …` must expose the same CLI.)
- [ ] No API keys in the repo. The grader will not have your key and does not need it.

## How to submit

1. Push your work to a **private** GitHub repository. Any name. Keep the history — we like
   seeing how you got there.
2. Add the GitHub user **`i95dev-grader`** as a collaborator (Settings → Collaborators → Add).
   Read access is enough.
3. Open the submission form: **<SUBMISSION_FORM_URL>**. Enter your email (the one we
   contacted you on), the repository URL, and optionally the commit SHA (default: HEAD of the
   default branch).
4. Within about 15 minutes you'll get an email with your score card: points per section and
   a short log of what the grader saw (which levels returned prices, which hidden tests
   failed and why, what the eval harness did under fault injection).

You may submit **three times**. The **last** submission is the one that counts, and the one
we review by hand. Attempts are logged with timestamps.

## What the autograder actually does

So there's no mystery:

1. Clones your repo at the given commit into a clean container (Python 3.11 / Node 20).
   `pip install -e .` (or `npm ci && npm run build`).
2. Starts `pricewatch-stores` locally with a **secret seed**.
3. **Stage 1 / Levels:** runs `pricewatch scan --stores-url … --out obs.jsonl` twice, a few
   seconds apart, then `pricewatch watch --history run1 --new run2`. Scores each store's
   prices against ground truth; scores "no false alerts". Watches the store logs for
   `robots.txt` violations and ignored `Retry-After`s (penalty).
4. **Stage 2:** runs `pricewatch watch` with our history fixtures and a rules file containing
   `below_median`, compares to the expected alert set for the `median_basis` you declared.
5. **Stage 3:** runs `pricewatch eval` with `PRICEWATCH_PROVIDER_PATH` set to our stub
   provider. The stub answers deterministically from `metadata["source_url"]`, and it will
   time out on some snapshots and return non-JSON on others. Checks that the harness survives,
   that `report.json` has the required keys with sane values, and scores
   `label_issues.json` against our answer key. Then runs `pricewatch extract --llm --provider anthropic`
   with our own Anthropic key on 40 product pages from two stores you have never seen, and scores
   what it prints against ground truth (ISSUE-3 Part C). Your code never sees that key's value
   beyond the environment variable, and the key is spend-capped and rotated.
6. Emails you the card and records the score.

Each step has a time limit (scan: 4 minutes; watch: 30 s; eval: 3 minutes). Anything that
hangs scores zero for that step, so respect the rate limits rather than fighting them.

## Common ways to lose points you didn't need to lose

- Renaming a CLI flag. The grader can't find it; the whole step scores zero.
- Hard-coding anything you observed under the public seed — markup, class names, the exact way a store lets a browser in. It changes with the seed.
- Hammering a store until it rate-limits you, then giving up. Slow down; the response tells you how long.
- An eval harness that raises on the first timeout. You lose 12 points of Stage 3 to one
  `try/except`.
- An LLM extractor whose prompt says "price in cents" and then meets a Japanese store. Yen has no cents.
- Leaving `median_basis` blank. We then assume the spec's definition; if you built the
  README's, every Stage 2 test fails.
- Listing every snapshot in `label_issues.json`. That scores zero by design.
