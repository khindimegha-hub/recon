# AI Ledger Reconciliation Engine

A reconciliation system that matches an internal transaction ledger against a bank/payment gateway statement — automatically resolving what it can prove with deterministic rules, and calling an LLM only for the residual cases that genuinely require judgment.

Built for Razorpay's AI Buildathon (AI Finance Controller track).

## The problem

Every business that touches money runs at least two independent records of the same transactions — an internal ledger and a bank or payment gateway statement. These drift out of sync constantly: settlement delays, rounding, duplicate retries, partial refunds, logging gaps. Today this gets reconciled by hand in spreadsheets, which doesn't scale and is error-prone. This project is a small, working version of that reconciliation layer.

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
Reconciliation Report
+ Streamlit Dashboard


## Design principle

**Deterministic rules handle everything provable. AI handles only what requires judgment.**

A ₹1 rounding difference or a 2-day settlement delay doesn't need an LLM call — a fixed rule explains it instantly, consistently, and for free. The LLM is only invoked on the residual exceptions no rule can confidently name (in this build: amount discrepancies too large to be rounding, with no other explanation). This keeps the system fast, cheap, and auditable — every classification either traces to a named rule or to a validated LLM response, never to an opaque black box.

This also reflects an explicit safety boundary: **the LLM never creates, modifies, or moves a financial transaction.** It only classifies exceptions and recommends a review action; all state changes remain deterministic.

## Stack

- **Python + pandas** — exact/fuzzy matching, rule-based classification
- **Groq API** (`openai/gpt-oss-20b`) — structured exception investigation, JSON-only output, schema-validated before use
- **Streamlit + Plotly** — dashboard
- **Synthetic data generator** — produces both datasets *and* a hidden ground-truth answer key, so accuracy is measured, not claimed

## Why a ground-truth answer key

Most hackathon reconciliation demos report a match rate and stop there. This one goes further: the data generator records the *true* reason behind every discrepancy before the engine ever sees it, so the engine's classifications can be scored against a real answer key afterward — not just eyeballed.

**Current benchmark (synthetic dataset, 66 ledger transactions):**
- Match rate: 97.0%
- Classification accuracy vs. ground truth: 94.6% (70/74 correctly explained)
- 7 of 74 total discrepancies were ambiguous enough to require LLM investigation; the rest were resolved by named rules alone

## Known limitations

- The LLM investigator sees only the two transaction records in isolation — no fee schedule, no historical baseline, no merchant-level pattern. In testing, this sometimes led it to guess "rounding error" for discrepancies too large to actually be rounding. With richer context (a fee table, historical variance per merchant), classification precision would improve. This is a scope decision made under a tight build deadline, not an unknown gap.
- Fuzzy matching currently pairs on merchant + amount/date tolerance with greedy first-match assignment; a production version would need conflict resolution when multiple candidates are plausible.
- Synthetic data only, at a small scale (dozens of transactions) — chosen deliberately to keep the ground-truth benchmark exact and the live demo fast, not because the approach doesn't scale. The matching logic itself is O(n) for the exact-match layer; the fuzzy layer is the part that would need optimization (e.g., blocking by merchant before pairwise comparison) at real transaction volumes.

## Running it

```bash
pip install -r requirements.txt
python src/generate_data.py      # generates ledger, statement, and ground truth
python src/reconcile.py          # deterministic matching + rule classification
python src/investigate.py        # full pipeline + LLM investigation (requires GROQ_API_KEY)
streamlit run src/dashboard.py   # visual dashboard
```

Set your Groq API key first: `$env:GROQ_API_KEY="your-key"` (PowerShell) or `export GROQ_API_KEY="your-key"` (bash).