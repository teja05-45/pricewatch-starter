# PriceWatch — i95Dev AI Engineering take-home

Welcome. This is the take-home for the AI Engineer (intern / entry-level) role at i95Dev.
You will inherit a small, working, slightly broken system, make it better, and prove that it
works. Everything you need is in this repo and its sibling, `pricewatch-stores`.

**Please read this whole page before you start. It is the single source of truth for how to
do the assignment and how it is graded.**

---

## 1. Use AI. Seriously.

We build software with AI every day and we expect you to as well. Use Claude, Cursor,
Copilot, ChatGPT, Gemini, an agent, whatever you like — for code, tests, debugging, reading
the codebase, writing your notes. There is no penalty and no "AI detection". We only ask
two things:

1. **You must understand what you submit.** After you submit, we'll do a 30-minute call
   where we change a requirement and watch you modify your own code. That call is the
   real test. Code you can't explain or extend will not help you.
2. **Tell us how you used it.** `DECISION_LOG.md` has a section for this. Honest
   specifics ("the model kept inventing a CSS selector that doesn't exist") are far more
   impressive to us than a polished story.

The assignment is built so that pasting the task into a chat window and shipping the answer
scores poorly. Not because the models are bad — because the tasks contain contradictions,
misleading hints, and bad data that only a person who reads and runs things will catch. That
person is who we're hiring.

## 2. What you're building

PriceWatch is a swarm of small agents that track prices across online stores:

```
scout ──► fetch ──► extractor ──► normalizer ──► history ──► watcher ──► alerts
   (find product URLs)   (HTML → data)  (money → cents)  (SQLite/JSONL)  (rules)
```

It watches five fake storefronts served by `pricewatch-stores`. They are deliberately arranged
from trivial to nasty, copying the kinds of friction real sites throw at automated clients. You
get a running instance and a README that describes *symptoms*; working out the mechanisms is
part of the assignment.

| Level | Store | What you'll notice |
|---|---|---|
| 1 | Corner Store | nothing — clean, well-structured HTML |
| 2 | Maple & Co | Shopify-like; European price formatting; sale items show two prices, but not always; variants, and the default isn't always first |
| 3 | Zon | marketplace; prices in pieces; nothing stable in the markup; several prices per page, one of them real; picks a variant first sometimes; suspicious of clients that don't *behave* like browsers, and silent about it |
| 4 | Shield Outfitters | won't let you in at first; a browser gets in after a moment; access is neither permanent nor portable; hates speed; price isn't findable by text search |
| 5 | Flux | single-page app; no prices in HTML; the API only talks to the app's own JavaScript; "amount" doesn't mean the same thing for every product; flaky; layout varies; prices really change |

The stores' README has a slightly longer version of this table and nothing more. Nothing is
hidden from you that a browser doesn't also have to deal with — open DevTools and watch.

**Do not scrape any real website for this assignment.** Everything runs against the fake stores.

## 3. Setup (10 minutes)

You need Python 3.10+ and Docker (or just use the hosted stores instance).

```bash
# 1. The fake internet (Docker; or use the hosted instance at <STORES_URL> for light development)
docker run --rm -p 4000:4000 -e STORE_SEED=public ghcr.io/i95dev/pricewatch-stores:latest
#    ^ leave this running. Change STORE_SEED to test against a catalogue you haven't seen.

# 2. This repo
cd ../pricewatch-starter
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                          # one test fails — that's expected
pricewatch scan --stores-url http://localhost:4000 --store corner
```

If the last command prints ten JSON lines with prices, you're set. Open
http://localhost:4000 in a browser and click around the five stores before writing any code.

For Stage 3: `pip install -e ".[llm]"` and export your own `ANTHROPIC_API_KEY` (or
`OPENAI_API_KEY` — develop with whichever you have). You pay for your own development usage; the
whole assignment should cost well under $2. Grading uses **our** Anthropic key against your
`--provider anthropic` path, so make sure that path works even if you developed with another provider.

## 4. The work

Everything is described in `tasks/`. Do them in order; each builds on the last.

| Stage | File | What | Time (guide) |
|---|---|---|---|
| 1 | `tasks/ISSUE-1.md` | A bug report about false alerts. Find and fix the real cause(s). | ~1.5 h |
| 1b | — | Climb the levels: make `pricewatch scan` return correct prices for as many of the five stores as you can. Each level is graded separately; partial credit is real. Levels 3–5 are where most of the time goes. | ~3 h |
| 2 | `tasks/ISSUE-2.md` | Add a `below_median` alert rule. The spec has a wrinkle. | ~1.5 h |
| 3 | `tasks/ISSUE-3.md` | LLM extraction for unknown stores **plus the eval that proves it works**. We grade the eval. | ~2 h |
| — | `DECISION_LOG.md` | One page: what you decided, what was wrong, what AI got wrong. Fill in the frontmatter — the grader reads it. | 20 min |

Guide total: 8–10 hours. You have **7 days** from receiving the link. Nobody expects all five
levels plus a perfect eval; we expect clear thinking about what you did and didn't do.

### Rules of the road

- Keep the CLI contract in `pricewatch/cli.py` stable — the autograder drives it.
  Add flags if you want; don't rename or remove what's there.
- Keep the `Observation` fields. Add fields if you want.
- Respect `robots.txt` and `Retry-After`. The grader watches for it.
- The existing tests are not gospel. If a test disagrees with what a store page actually shows, the page wins — and say so in the log.
- Don't hard-code product ids, prices, markup details or anything else you observed under one seed. The grader uses a different seed, and the seed changes more than the catalogue.
- Python is the starter. If you'd rather work in TypeScript, you may port the whole thing —
  the autograder only talks to the CLI — but you take on the port time yourself.

### Alert rules (reference)

Rules live in `alerts.yaml` and are evaluated by `agents/watcher.py` after each scan.

- `drop_pct` — fires when the price falls at least `pct` percent versus the previous observation.
- `below_median` — (ISSUE-2) fires when the price is at least `pct` percent below the
  product's median over the trailing `window_days`. The median is taken over daily closing
  prices — the last observation on each day — so that a day with many scans doesn't
  outweigh a day with one.

## 5. Submitting and grading

Read `SUBMISSION.md`. Short version: push to a **private** GitHub repo, invite our grader
account, submit the URL on the form, get a score card by email within ~15 minutes. You can
submit **three times**; the last submission counts. Use the first one early — it's the
cheapest way to find out you misread something.

Scoring (100):

| Points | What | How |
|---|---|---|
| 20 | Stage 1 | hidden tests: no false alerts; correct Maple prices |
| 20 | Levels 1–5 extraction | hidden product set; weighted by level (L1 = 1 … L5 = 6) |
| 15 | Stage 2 | hidden history fixtures; either median basis accepted **if declared** in `DECISION_LOG.md` |
| 20 | Stage 3 | 12: harness survives our fault-injecting provider, report schema, `label_issues.json` vs. answer key · 8: **your** LLM extractor run with **our Anthropic key** (`--provider anthropic`) on 40 never-seen pages from two unknown stores |
| 10 | Code & design | human-read: is this a codebase you'd want to inherit? |
| 5 | Decision log | human-read: clarity, honesty, specificity |
| 10 | Walkthrough | live 30 min; a change to a requirement, you make it |

The first 75 points are automatic and drive who we talk to. The last 25 are read by an
engineer for candidates above the bar. The walkthrough is a gate: a great score and a
walkthrough where you can't move in your own code is a no.

## 6. Questions

Email the address on the form. We answer questions about setup and about the grader within
one working day. We don't answer questions about which interpretation of a spec is "right" —
deciding that and writing down why is part of the job.

Good luck. Have fun with it — most people who finish this keep the repo.
