# Recon — AI Ledger Reconciliation Engine

Recon reconciles an internal transaction ledger against a bank or payment gateway statement. It resolves everything it can prove with deterministic rules, and only calls an LLM for the exceptions that genuinely require judgment. Built for Razorpay's AI Buildathon, Track 04: AI Finance Controller.

## Why this problem

Any business that touches money ends up with at least two independent records of the same transactions — what its own system logged, and what the bank or payment gateway actually shows. These two records drift apart constantly: a payment settles two days late, a fee gets deducted that wasn't accounted for, a retry creates a duplicate, a refund never makes it back into the ledger. Matching the obvious cases is trivial. The actual work in reconciliation is deciding what to do with everything that doesn't match cleanly, and today that's mostly done by hand in spreadsheets.

## Approach

The core decision I made early on was to not send every transaction to an LLM. If a rule can prove the answer — an exact ID match, a difference small enough to be rounding, a settlement delay within a normal window — there's no reason to pay for a model call or accept the unpredictability that comes with one. The LLM only gets involved once the deterministic layer has genuinely run out of explanations.

```
Ledger + Statement
        |
        v
  Exact match (transaction ID)
        |
        v
  Fuzzy match (merchant + amount/date tolerance)
        |
        v
  Rule-based classification
  (rounding, date shift, duplicate, missing)
        |
   ------------------
   |                |
confidently      genuinely
classified       ambiguous
   |                |
   |                v
   |          LLM investigation
   |          (structured, confidence-scored)
   |                |
   |         ---------------
   |         |             |
   |    confidence >=   confidence <
   |       0.85            0.85
   |         |             |
   |    auto-resolve   escalate to human
   |         |             |
   -------------------------
              |
              v
     Reconciliation report
     + audit JSON + dashboard
```

Once an exception reaches the LLM, its output isn't taken at face value either. It returns a classification, the evidence it based that on, a recommended action, and a confidence score, and that response is validated against a schema before anything uses it — a malformed or incomplete response falls back to "needs manual review" rather than being trusted. The confidence score itself then drives one more decision: above 0.85, the system auto-resolves the case; below it, the case is escalated to a human. At no point does the model touch a transaction directly. It classifies and recommends; the routing logic decides what happens next.

## Results

On a synthetic benchmark of 66 ledger transactions (74 total classified items once you include statement-only exceptions), scored against a hidden ground-truth answer key built into the data generator rather than eyeballed after the fact:

| Metric | Result |
|---|---|
| Match rate | 97.0% |
| Classification accuracy vs. ground truth | 94.6% (70/74) |
| Resolved without AI | 90.5% (67/74) |
| Cases sent to AI investigation | 7 |
| Of those, auto-resolved by confidence routing | typically 6 |
| Escalated to human review | typically 1 |
| Requiring zero human action overall | 73/74 |
| Deterministic throughput | 500–3,000+ transactions/sec, varying by machine load |

I'm calling out that the AI auto-resolve/escalate split varies slightly between runs, because it does — a language model isn't perfectly deterministic between calls, so a transaction that scores 0.86 confidence one run might score 0.83 the next and land on the other side of the threshold. That's expected behavior, not a bug, and worth being upfront about rather than presenting one run's numbers as fixed.

## What the LLM actually sees, and what it doesn't

The investigator gets exactly two things: the ledger record and the statement record for one transaction, nothing else. No fee schedule, no history for that merchant, no context about typical settlement patterns. That's a real limitation — in testing, it would sometimes guess "rounding error" for a gap of several hundred rupees, which is too large to plausibly be rounding. Giving it a fee table or a merchant-level baseline would very likely fix this, but that's future work, not something this build does. I'd rather say that plainly than let the number speak for itself.

Other things I know are incomplete: the fuzzy matcher uses a first-valid-match strategy and doesn't try to find a globally optimal pairing when several candidates are similar. The 0.85 confidence threshold is a reasonable starting point, not something calibrated against real labeled outcomes. There's no automated test suite yet. And this all runs against synthetic data at a small scale — chosen deliberately so the ground-truth benchmark stays exact and the demo stays fast, not because the matching logic itself couldn't handle more.

## What actually broke while building this

- **pandas `Timestamp` objects aren't JSON-serializable.** The date column needs to stay a `Timestamp` for the date-tolerance math elsewhere in the pipeline, but that same object can't go straight into `json.dumps` when a record gets sent to the LLM. Fixed with one small conversion function right before serialization, rather than changing how dates are loaded everywhere.

- **Ran out of API credit on my first LLM provider.** I didn't have budget to add more, so I switched the investigator from Anthropic to Groq's free tier. Because the investigation function had a clean interface — records in, a validated dict out — swapping providers meant changing the client and model name, and nothing else in the pipeline had to change.

- **Guessed two model names that didn't exist on my account** and got 404s for both. Stopped guessing, queried Groq's actual model list for the account, and used the exact string it returned.

- **A dashboard theme config that should have made native charts and tables dark just didn't apply**, and I couldn't pin down why quickly. Rather than keep debugging a framework default, I rebuilt the chart in Plotly and the table as plain HTML, with every color set explicitly in code, so there was nothing left for a theme system to silently override.

- **The dashboard once displayed zero human escalations when the real run had one.** The reconciliation logic was correct — the bug was in how the dashboard read the generated audit JSON. It was looking for a nested structure that the report never actually used, so the lookup silently failed and fell back to assuming nothing had been escalated. I caught it by comparing the dashboard's displayed numbers directly against the terminal output for the same run, rather than trusting that a plausible-looking dashboard meant a correct one. That's probably the most useful thing this build taught me: a number that looks reasonable isn't the same as a number that's actually right, and the only way to know the difference is to check it against the source.

## Stack

Python and pandas for the deterministic matching and rule classification. Groq's API (`openai/gpt-oss-20b`) for the LLM investigation step, called only on the residual ambiguous cases. Streamlit and Plotly for the dashboard. A synthetic data generator that produces the ledger, the statement, and a hidden ground-truth file all at once, so the engine's own accuracy can be measured rather than assumed.

## Project structure

```
recon/
├── data/
│   ├── bank_statement.csv
│   ├── ground_truth.csv
│   ├── internal_ledger.csv
│   └── reconciliation_report.json
├── src/
│   ├── generate_data.py
│   ├── reconcile.py
│   ├── llm_investigator.py
│   ├── investigate.py
│   └── dashboard.py
├── requirements.txt
└── README.md
```

## Running it

```bash
git clone https://github.com/khindimegha-hub/recon.git
cd recon
pip install -r requirements.txt

python src/generate_data.py      # builds the ledger, statement, and ground truth
python src/reconcile.py          # deterministic matching, rule classification, throughput
python src/investigate.py        # full pipeline + LLM investigation + confidence routing
streamlit run src/dashboard.py   # dashboard
```

`investigate.py` needs a Groq API key set as an environment variable before it can reach the LLM:

```bash
export GROQ_API_KEY="your-key-here"        # macOS/Linux
$env:GROQ_API_KEY="your-key-here"          # Windows PowerShell
```

Without a key, it still runs — every ambiguous case just falls back to "needs manual review" instead of crashing, which is the same fallback behavior it uses if the API call itself fails for any other reason.

## Repository

https://github.com/khindimegha-hub/recon