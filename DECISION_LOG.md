---
# Machine-read by the autograder. Keep the keys; fill in the values.
name: "i95Dev Candidate"
median_basis: "daily_close"        # "observations" or "daily_close" — see README "Alert rules" vs tasks/ISSUE-2.md
levels_attempted: [1, 2, 3, 4, 5]    # e.g. [1, 2, 3, 4, 5]
llm_provider: "anthropic"        # e.g. "openai", "anthropic", "gemini", "groq"
llm_model: "claude-haiku-4-5"
ai_tools_used: ["Antigravity", "Gemini 3.6 Flash"]
hours_spent: 8
---

# Decision log

## Stage 1 — what was actually wrong
- **Maple & Co Extractor Bug**: `extract_maple()` in `pricewatch/agents/extractor.py` used `soup.select_one(".price .price")`, which matched `.price--compare` (`937,20 €`) instead of `.price--sale` (`720,92 €`).
- **European Currency Normalization Bug**: `parse_money()` in `pricewatch/agents/normalizer.py` used `re.sub(r"[^\d.]", "", text)`, stripping European comma decimal separators and treating `"937,20 €"` as `93720.0` (9,372,000 cents) instead of `937.20` (93,720 cents).
- **Watcher Percentage Bug**: `rule_drop_pct()` in `pricewatch/agents/watcher.py` calculated `(prev - cur) / cur * 100` (dividing by `cur` instead of `prev`).
- **Ops Theory Evaluation**: Ops correctly noticed inflated drop percentages, but missed the underlying extractor selector and normalizer locale parsing bugs that caused initial baseline test failures.

## Stage 2 — the median
- **Discrepancy Resolution**: `README.md` specified taking the median over daily closing prices (last observation of each calendar day), whereas `tasks/ISSUE-2.md` described taking the median over all observations in the trailing window.
- **Choice**: Followed `daily_close` aggregation to prevent high-frequency scan bursts on a single day from distorting the true historical price baseline. Declared `median_basis: "daily_close"` in frontmatter.
- **Days with no observations**: Excluded from the median calculation. Minimum threshold of $\ge 3$ distinct daily observations in the trailing window enforced before firing `below_median` alerts.

## Levels 3–5 — how you got in
- **Level 3 (Zon)**: Replaced seed-dependent static CSS class names (`ZON_CLASSES`) with dynamic HTML structural selectors, regex price matching (`$XX.YY` and whole/fraction element grouping), pack-size extraction from title text, and robot check detection.
- **Level 4 (Shield Outfitters)**: Solved the custom 503 challenge barrier (`<div id="cf-c" data-s="..." data-p="...">`) by computing SHA-256(`s|p`)[:16], waiting 1.35s / respecting `Retry-After`, POSTing payload `{"s": s, "p": p, "a": answer}` to the root challenge endpoint `/stores/shield/challenge`, storing returned `shield_clearance` cookies in `Client.session`, locking thread access via `_challenge_lock`, and extracting non-text-searchable client-rendered prices and titles from embedded `window.__STATE__` JSON scripts (product object and prices map) with fallback to DOM attributes.
- **Level 5 (Flux)**: Completed full SPA GraphQL API extraction by parsing `<div class="pdp" data-sku="...">` and `<meta name="flux-build" content="...">`, generating signature `SHA-256("fx_1b11e1e8cfb25a950a27|" + sku)[:24]`, making POST requests to `/stores/flux/api/graphql` with `x-flux-sig` and `x-flux-build` headers, handling `unit: major` vs `minor` price calculation, `stale` price flags, and script fallback.

## Stage 3 — what the model got wrong
- **Failure Patterns**: Models occasionally confused compare-at prices with current prices when both were present in raw HTML, or extracted monthly EMI/installment amounts on Indian marketplace pages (`bazaario`).
- **Mislabeled Snapshots**: Identified `bz-052` as mislabeled in `eval/labels.json` (`bz-052` recorded the monthly EMI amount `60200` instead of the actual product price `1806200`).
- **Provider Architecture**: Implemented model-agnostic extraction prompt and strict JSON schema validation layer. Added `GroqProvider` and `GeminiProvider` for local development while preserving full `--provider anthropic` (`ANTHROPIC_API_KEY`) compatibility for official grading.

## Where AI helped and where it didn't
- **Helped**: AI excelled at drafting comprehensive unit tests for normalizer edge cases, generating light-theme CSS for the dashboard, and formulating regex patterns for currency detection.
- **Didn't Help**: AI initially attempted to fix `test_watcher.py` by changing the assertion without fixing the underlying formula, and suggested static CSS selectors for Zon that broke on seed changes. Hand-crafted structural parsing was required.

## If I had another day
- Add automated browser challenge solvers (e.g. Playwright fallback for Level 4/5 edge cases).
- Add real-time WebSocket price drop notifications to the frontend UI dashboard.
- Implement adaptive LLM prompt compression to reduce input token cost on massive HTML snapshots.
