# PriceWatch Implementation Notes

## 1. Initial Baseline
- **pytest status**: 9 collected, 8 passed, 1 failed.
  - Failure: `tests/test_extractor_maple.py::test_maple_sale_item_reports_sale_price` (`AssertionError: 9372000 == 72092`).
- **CLI Connection Status**: Running `pricewatch scan --stores-url http://localhost:4000 --store corner` produced `ConnectionRefusedError [WinError 10061]` because the local fake store service was not running on port 4000.

---

## 2. Maple Sale Price Bug
- **Root Cause 1**: `extract_maple()` in `pricewatch/agents/extractor.py` targeted `.price .price`, which matched `.price--compare` (`937,20 €`) instead of `.price--sale` (`720,92 €`).
- **Root Cause 2**: `parse_money()` in `pricewatch/agents/normalizer.py` used `re.sub(r"[^\d.]", "", text)`, stripping European comma decimal separators and treating `"937,20 €"` as `93720.0` (9,372,000 cents) instead of `937.20` (720.92 = 72,092 cents).
- **Fix Implemented**:
  - Redesigned `parse_money()` to detect European format (comma followed by 1 or 2 digits) vs US format (period decimal separator) vs zero-decimal currencies (`JPY`).
  - Updated `extract_maple()` to target `.price--sale` for current price and `.price--compare` for compare-at price.
  - Added regression test suite covering European decimal formatting, zero-decimal currencies, and missing/malformed price strings.

---

## 3. Local Fake Store Connection
- **Root Cause**: `WinError 10061` occurred because no server was listening on port 4000.
- **Service Requirement**: `ghcr.io/i95dev/pricewatch-stores:latest` or local `npm run dev` in `pricewatch-stores`.
- **CLI Handling Improvement**: Wrapped `requests.exceptions.ConnectionError` in `pricewatch/cli.py` to display concise, actionable guidance explaining how to start the fake store server, while preserving full tracebacks under `--debug`.

---

## 4. Issue 1 — Price Drop Alert Bug
- **Root Cause**: `rule_drop_pct()` in `pricewatch/agents/watcher.py` calculated percentage drop as `(prev - cur) / cur * 100` (dividing by `cur` instead of `prev`).
- **Fix**: Corrected formula to `(prev.price_cents - cur.price_cents) / prev.price_cents * 100`. Updated `test_watcher.py` assertion to verify the correct `20.0% drop` (10000 -> 8000).
- **Regression Tests**: Covered price drops, increases, zero prices, currency mismatches, and multiple observations.

---

## 5. Issue 2 — Below Median Alert
- **Median Basis Choice**: Evaluated ambiguity between `README.md` ("daily closing prices") and `tasks/ISSUE-2.md` ("all observations in trailing window"). Chose `daily_close` aggregation to eliminate single-day scan burst distortions. Declared `median_basis: "daily_close"` in `DECISION_LOG.md`.
- **Rule Constraints Implemented**:
  - Evaluated over trailing `window_days` excluding current observation.
  - Required $\ge 3$ valid daily closing observations.
  - Enforced currency uniformity.
  - Computed integer median rounded to nearest cent.
  - Resolved rule priority: `below_median` takes precedence over `drop_pct`.

---

## 6. Store Extraction (Levels 1–5)
- **Level 1 (Corner)**: Schema.org JSON-LD parsing with fallback to HTML elements.
- **Level 2 (Maple)**: European price formatting, sale vs compare-at price separation, stock availability.
- **Level 3 (Zon)**: Replaced static seed classes (`ZON_CLASSES`) with dynamic HTML structure parsing, whole/fraction split element extraction, regex pack size parsing (`Pack of X`), and robot check detection.
- **Level 4 (Shield Outfitters)**: Solved access challenge barrier by parsing `<div id="cf-c" data-s="..." data-p="...">`, calculating SHA-256(`s|p`)[:16], waiting 1.35s / respecting `Retry-After`, POSTing solution payload to root challenge endpoint `/stores/shield/challenge`, storing `shield_clearance` cookie in `Client.session`, and adding thread synchronization `_challenge_lock` to avoid multi-thread challenge stampedes. Implemented non-text-searchable dynamic client rendering extraction by parsing `window.__STATE__` JSON payloads (`product` and `prices` maps) containing product title, amount (in minor units), currency, compare-at price, and stock status.
- **Level 5 (Flux)**: Full SPA dynamic GraphQL API extraction. Discovers product SKU from `<div class="pdp" data-sku="...">` and build token from `<meta name="flux-build" content="...">`. Generates signature `SHA-256("fx_1b11e1e8cfb25a950a27|" + sku)[:24]`, posts GraphQL query to `/stores/flux/api/graphql` with `x-flux-sig` and `x-flux-build` headers, handles `unit == "major"` vs `"minor"` units, extracts stock availability, flags `stale` prices in observation notes, and falls back to JSON script tag parsing if GraphQL fails.

---

## 7. LLM Fallback
- **Provider Architecture**: Maintained normalized `Provider` interface. Preserved mandatory `--provider anthropic` (`ANTHROPIC_API_KEY`) and `openai` (`OPENAI_API_KEY`) paths. Added `GroqProvider` (`GROQ_API_KEY`) and `GeminiProvider` (`GEMINI_API_KEY`) for local development.
- **Prompt Engineering**: Instructed model to identify actual product selling price, ignore compare-at/MSRP/EMI/shipping numbers, detect currencies, and output strict JSON.
- **Validation Layer**: Stripped markdown code blocks, handled malformed JSON gracefully, and validated numeric ranges and currency codes.

---

## 8. Evaluation
- **Benchmark Metrics**: Evaluated 90 snapshots across `nordkart` and `bazaario`.
- **Fault Tolerance**: Wrapped snapshot evaluation in exception handlers. Snapshots hitting provider timeouts, provider errors, or JSON decode errors score 0.0 without crashing the harness.
- **Disk Caching**: Cached snapshot completions under `eval/out/.cache/` (or `eval/.cache/`) to eliminate duplicate API expenditure.
- **Label Issues**: Identified snapshot `bz-052` as mislabeled in `eval/labels.json` (recorded monthly EMI amount `60200` instead of selling price `1806200`). Saved output to `eval/out/label_issues.json`.

---

## 9. Testing
- **Suite Results**: 48 pytest unit and integration tests passing cleanly across 10 test modules.
- **Coverage**: Extractor adapters (Corner, Maple, Zon, Shield, Flux), normalizer, watcher alert rules, LLM prompt parsing, provider injection, evaluation harness fault tolerance, Shield 503 challenge solver & `window.__STATE__` JavaScript payload parsing, Flux GraphQL API signature calculation, UTF-8 file handling, and HTTP server dashboard endpoints.

---

## 10. Docker Setup
- Verified `Dockerfile` using `python:3.11-slim` with `pip install -e ".[dev,llm]"`.
- Verified `docker-compose.yml` orchestrating `pricewatch-stores` (port 4000) and `pricewatch-app` (port 8000).

---

## 11. UI/UX Dashboard
- Built a modern, responsive **WHITE/LIGHT THEME** SaaS analytics interface using Inter typography, metric cards, status pills, price tables, and health indicators powered by live SQLite database queries.

---

## 12. Production Deployment
- Detailed deployment steps covering Docker containers, environment variables, health check endpoints (`/health`), storage persistence (`pricewatch.db`), and load balancer configuration in `README.md`.

---

## 13. AI Tools Used
- Utilized Google Antigravity & Gemini 3.6 Flash for pair programming, regex formulation, test suite generation, and light-theme UI design.

---

## 14. Known Limitations
- Shield / Flux full dynamic client-side JS execution relies on JSON/script payload inspection and HTTP API endpoints; complex obfuscated WASM challenges would require headless browser integration (e.g., Playwright).
