# Recon — AI Ledger Reconciliation Engine

A reconciliation system that matches an internal transaction ledger against a bank/payment gateway statement — automatically resolving what it can prove with deterministic rules, and calling an LLM only for the residual cases that genuinely require judgment.

Built for Razorpay's AI Buildathon (AI Finance Controller track).

## The problem

Every business that touches money runs at least two independent records of the same transactions — an internal ledger and a bank or payment gateway statement. These drift out of sync constantly: settlement delays, rounding, duplicate retries, partial refunds, logging gaps. Today this gets reconciled by hand in spreadsheets, which doesn't scale and is error-prone. Recon is a small, working version of that reconciliation layer.

## Live demo

Run `streamlit run src/dashboard.py` for the dashboard, or `python src/investigate.py` for the full pipeline with LLM output in the terminal.

## Architecture
Ledger CSV Statement CSV
│ │
└────────┬───────────┘
▼
Exact Match (txn_id)
▼
Fuzzy Match (merchant + amount/date tolerance)
▼
Rule-Based Classification
(rounding, date_shift, duplicate,
missing_in_ledger, missing_in_statement)
▼
┌─────────┴─────────┐
▼ ▼
Confidently Genuinely
classified ambiguous
(no LLM call) ▼
│ LLM Investigator
│ (structured JSON,
│ schema-validated)
└─────────┬─────────┘
▼
Confidence-Based Routing
(auto-resolve or escalate
to human review)
▼
Reconciliation Report
+ Audit JSON + Dashboard

## Design principle

**Deterministic rules handle everything provable. AI handles only what requires judgment.**

A ₹1 rounding difference or a 2-day settlement delay doesn't need an LLM call — a fixed rule explains it instantly, consistently, and for free. The LLM is only invoked on the residual exceptions no rule can confidently name (in this build: amount discrepancies too large to be rounding, with no other explanation). This keeps the system fast, cheap, and auditable — every classification either traces to a named rule or to a validated LLM response, never to an opaque black box.

This also reflects an explicit safety boundary: **the LLM never creates, modifies, or moves a financial transaction.** It only classifies exceptions and recommends a review action; all state changes remain deterministic.

### Where the AI acts as an agent, and where it deliberately doesn't

The LLM component (`llm_investigator.py`) functions as a bounded investigator agent: given an ambiguous exception, it independently decides how to classify it, what evidence supports that classification, and what action to recommend — without a human writing that logic case-by-case. Its output then drives a real decision: `investigate.py` routes each investigated case based on the AI's own confidence score — auto-resolved above 0.85, escalated to human review below it — so the system closes the loop instead of just producing a recommendation nobody acts on. Its authority is still deliberately narrow: it cannot query additional data sources, retry with a different strategy, or take any action beyond returning a structured recommendation and a routing decision. Every other stage of the pipeline (matching, rule classification, metric scoring) is intentionally non-agentic — fixed, auditable logic, because those are cases where a deterministic answer already exists and an agent would add risk without adding value.

## Stack

- **Python + pandas** — exact/fuzzy matching, rule-based classification
- **Groq API** (`openai/gpt-oss-20b`) — structured exception investigation, JSON-only output, schema-validated before use
- **Streamlit + Plotly** — dashboard
- **Synthetic data generator** — produces both datasets *and* a hidden ground-truth answer key, so accuracy is measured, not claimed

## Why a ground-truth answer key

Most hackathon reconciliation demos report a match rate and stop there. Recon goes further: the data generator records the *true* reason behind every discrepancy before the engine ever sees it, so the engine's classifications can be scored against a real answer key afterward — not just eyeballed.

**Current benchmark (synthetic dataset, 66 ledger transactions):**
- Match rate: 97.0%
- Classification accuracy vs. ground truth: 94.6% (70/74 correctly explained)
- Throughput: 1,700+ transactions/sec for the deterministic layer
- 7 of 74 total discrepancies were ambiguous enough to require LLM investigation; the rest were resolved by named rules alone
- Of those 7: 6 auto-resolved by AI confidence routing, 1 escalated to human review — **73 of 74 total items required zero human action**

## Known limitations

- The LLM investigator sees only the two transaction records in isolation — no fee schedule, no historical baseline, no merchant-level pattern. In testing, this sometimes led it to guess "rounding error" for discrepancies too large to actually be rounding. With richer context (a fee table, historical variance per merchant), classification precision would improve. This is a scope decision made under a tight build deadline, not an unknown gap.
- Fuzzy matching currently pairs on merchant + amount/date tolerance with greedy first-match assignment; a production version would need conflict resolution when multiple candidates are plausible.
- Synthetic data only, at a small scale (dozens of transactions) — chosen deliberately to keep the ground-truth benchmark exact and the live demo fast, not because the approach doesn't scale. The matching logic itself is O(n) for the exact-match layer; the fuzzy layer is the part that would need optimization (e.g., blocking by merchant before pairwise comparison) at real transaction volumes.
- The 0.85 auto-resolve confidence threshold is a reasonable starting point, not a tuned value — a production version would calibrate this against labeled outcomes over time.

## What broke, and how I got out

Real problems hit during the build, in order:

1. **`TypeError: Object of type Timestamp is not JSON serializable`** — pandas loads the `date` column as a `Timestamp` object (needed for date-tolerance math elsewhere in the pipeline), but that same object can't be passed to `json.dumps` when sending a record to the LLM. Fixed by converting to a plain date string right before serialization, in one dedicated function (`_to_serializable`), rather than changing how dates are loaded everywhere else and risking breaking the matching logic.

2. **Anthropic API returned a 400 — insufficient credit balance.** No budget to add credits. Rather than block on it, switched the LLM investigator to Groq's free tier. Since `investigate_exception()` was already written as a single function with a clean interface (input records in, validated dict out), swapping providers meant changing the client and model name only — nothing else in the pipeline needed to change at all.

3. **Guessed model names that didn't exist on the account (`llama-3.3-70b-versatile`, then `llama-3.1-8b-instant`) — both 404'd.** Stopped guessing and queried the account's actual available models directly via Groq's `/models` endpoint, then used the exact string it returned (`openai/gpt-oss-20b`). Confirmed working on the first try after that.

4. **Dashboard's chart and table kept a white background despite a dark theme config that should have overridden it.** Rather than keep patching a framework default that wasn't behaving as documented, switched to a chart library (Plotly) and a hand-built HTML table where every color is set explicitly in code — removing the dependency on theme inheritance working correctly at all.

5. **Dashboard's "Total Transactions" and match rate briefly disagreed with the CLI report** (86.5% vs. 97.0%) — traced to a metric calculation that summed two differently-sized datasets together. Fixed by reusing the same `total = len(ledger)` definition the CLI report already used.

6. **A near-identical bug resurfaced in the loop-closure summary** ("67 resolved" out of "66 total" — a number exceeding its own denominator). Same root cause as #5: blending two differently-scoped counts into one number. Fixed by explicitly labeling and reporting both denominators separately instead of forcing one number to represent two different things.

The common thread: every fix kept the interface between components stable (same function signatures, same return shapes) so a fix in one layer never cascaded into rewriting the others — and the same class of bug (blending two different-sized populations into one count) showed up twice, which is itself a useful lesson about being consistent with what a "total" means across a codebase.

## Running it

```bash
pip install -r requirements.txt
python src/generate_data.py      # generates ledger, statement, and ground truth
python src/reconcile.py          # deterministic matching + rule classification + throughput
python src/investigate.py        # full pipeline + LLM investigation + confidence-based routing (requires GROQ_API_KEY)
streamlit run src/dashboard.py   # visual dashboard
```

Set your Groq API key first: `$env:GROQ_API_KEY="your-key"` (PowerShell) or `export GROQ_API_KEY="your-key"` (bash).