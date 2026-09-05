Yes — here is the **entire README as one single code block**, ready to copy directly into `README.md` in VS Code.

````markdown
# Recon — AI Ledger Reconciliation Engine

Recon reconciles an internal transaction ledger against a bank or payment gateway statement. It resolves everything it can prove with deterministic rules, and only calls an LLM for the exceptions that genuinely require judgment.

Built for **Razorpay's AI Buildathon — Track 04: AI Finance Controller**.

---

## Why this problem

Any business that touches money ends up with at least two independent records of the same transactions — what its own system logged, and what the bank or payment gateway actually shows.

These two records drift apart constantly:

- A payment settles two days late
- A fee gets deducted that wasn't accounted for
- A retry creates a duplicate
- A refund never makes it back into the ledger
- A transaction exists in one system but not the other

Matching the obvious cases is easy.

The actual work in reconciliation is deciding what to do with everything that doesn't match cleanly, and today that is still largely handled manually.

Recon is designed to reduce that unnecessary manual work while keeping humans in control of uncertain cases.

---

## Approach

The main decision I made early on was:

> **Don't send every transaction to an LLM.**

If a rule can prove the answer — such as an exact transaction ID match, a small rounding difference, or a date shift within an acceptable window — there is no reason to make an AI call.

The LLM only gets involved after the deterministic layer has genuinely run out of explanations.

The overall workflow is:

```text
Ledger + Statement
        |
        v
Exact Match
(transaction ID)
        |
        v
Similarity / Tolerance Matching
(merchant + amount + date)
        |
        v
Rule-Based Classification
(rounding / date shift / duplicate / missing)
        |
        +-----------------------------+
        |                             |
        v                             v
   Clearly classified          Genuinely ambiguous
        |                             |
        |                             v
        |                       LLM Investigation
        |                       (structured output)
        |                             |
        |                    +--------+--------+
        |                    |                 |
        |              confidence >= 0.85   confidence < 0.85
        |                    |                 |
        |                    v                 v
        |               Auto-resolve      Human review
        |                    |                 |
        +--------------------+-----------------+
                             |
                             v
                  Reconciliation Report
                  + Audit JSON + Dashboard
````

This gives Recon a simple operating principle:

> **Deterministic first. AI second. Human last.**

---

## Deterministic matching

The reconciliation engine first tries to resolve transactions without using AI.

It considers:

* Exact transaction ID matches
* Amount comparison
* Date tolerance
* Merchant-name normalization
* Transaction similarity
* Duplicate detection
* Missing-record detection

The goal is to resolve as much as possible with rules that are:

* Fast
* Explainable
* Repeatable
* Easy to audit

If the answer can be proven with deterministic logic, the transaction never reaches the LLM.

---

## Exception classification

Transactions that cannot be cleanly matched are classified into meaningful exception categories.

Examples include:

* Clean match
* Rounding difference
* Amount mismatch
* Date shift
* Duplicate in statement
* Missing in ledger
* Missing in statement

Instead of simply returning:

```text
NOT MATCHED
```

Recon tries to answer:

```text
WHY was this not matched?
```

That classification is then used to determine whether the case can be resolved automatically or requires further investigation.

---

## LLM investigation

The LLM is only used for genuinely ambiguous cases.

For each ambiguous case, the investigator receives the relevant ledger record and statement record.

The expected output contains:

```text
classification
explanation
recommendation
confidence
```

The response is validated against a schema before it is used.

If the response is malformed or incomplete, the system does not trust it.

Instead, the case falls back to:

```text
Needs manual review
```

This is intentional.

The LLM is an investigator, not the final decision-maker.

---

## Confidence-based routing

Recon uses an **85% confidence threshold** for AI-assisted decisions.

```text
AI confidence >= 0.85
        |
        v
   Auto-resolve


AI confidence < 0.85
        |
        v
   Human review
```

The confidence score therefore becomes a routing mechanism rather than just a number displayed on the dashboard.

An important principle here is:

> **An AI saying "I don't know" is safer than an AI confidently making the wrong decision.**

---

## Financial safety

The LLM does not have direct control over financial operations.

It cannot:

* Move money
* Edit the ledger
* Approve payments
* Initiate refunds
* Initiate settlements
* Delete financial records

Its role is limited to:

```text
Investigation
     +
Recommendation
     +
Confidence
```

The application logic decides what happens next.

When confidence is insufficient, the case goes to a human.

This keeps the AI inside a controlled finance-ops workflow rather than allowing it to directly perform financial actions.

---

## Results

Recon was evaluated on a synthetic benchmark containing:

* **66 ledger transactions**
* Additional statement-side records
* **74 total classified items**

The benchmark is scored against a ground-truth answer key generated alongside the synthetic data.

This means the results are measured against known expected outcomes rather than being manually judged after the run.

| Metric                                   |                          Result |
| ---------------------------------------- | ------------------------------: |
| Reconciliation coverage                  |                       **97.0%** |
| Classification accuracy vs. ground truth |               **94.6% (70/74)** |
| Resolved without AI                      |               **90.5% (67/74)** |
| Cases sent to AI investigation           |                           **7** |
| AI auto-resolved                         |                 **Typically 6** |
| Escalated to human review                |                 **Typically 1** |
| Requiring zero human action overall      |                       **73/74** |
| Deterministic throughput                 | **500–3,000+ transactions/sec** |

### About the AI results

The AI auto-resolve / escalation split can vary slightly between runs.

That is expected because language-model responses are not perfectly deterministic.

For example, a transaction that receives a confidence score of `0.86` in one run could receive `0.83` in another run and therefore cross the routing threshold in a different direction.

I am intentionally reporting this variation rather than presenting one particular run as a guaranteed fixed result.

---

## What the LLM actually sees

The investigator receives only the relevant records for one ambiguous transaction:

```text
Ledger record
+
Statement record
```

It does not receive:

* Merchant history
* Fee schedules
* Historical settlement patterns
* Other transactions from the merchant
* External financial context

This is a deliberate limitation of the current implementation.

Because the model has limited context, it can sometimes make an incorrect assumption.

For example, during testing it could classify a difference of several hundred rupees as a rounding issue, even though that amount is too large to plausibly be explained by normal rounding.

A future version could provide additional context such as:

* Fee tables
* Merchant-level baselines
* Settlement rules
* Historical transaction patterns
* Known gateway behavior

Those are future improvements rather than capabilities claimed by the current build.

---

## Known limitations

Recon is intentionally a focused prototype, so there are several limitations.

### 1. First-valid fuzzy matching

The fuzzy matcher currently uses a first-valid-match strategy.

It does not attempt to find a globally optimal pairing when multiple transactions have similar candidates.

### 2. Confidence threshold

The `0.85` confidence threshold is a reasonable starting point.

It has not been calibrated against a large set of real labeled financial outcomes.

### 3. Synthetic data

The current benchmark uses synthetic financial data.

This keeps the ground truth exact and makes the demonstration reproducible, but real-world financial data would contain more complex edge cases.

### 4. Limited LLM context

The LLM only receives the ledger and statement records relevant to the individual exception.

It does not have access to broader merchant or financial context.

### 5. Test coverage

The project does not yet have a comprehensive automated test suite.

---

## What actually broke while building this

This project also involved several practical engineering problems.

### Pandas timestamps and JSON

Pandas `Timestamp` objects are useful for date calculations but are not directly JSON serializable.

The solution was to keep timestamps in their normal form during reconciliation and convert them only at the serialization boundary.

This avoided changing the data representation throughout the rest of the pipeline.

---

### LLM API credit limitations

The first LLM provider I used ran out of available API credit.

Instead of adding more paid usage, I moved the investigator to Groq's free tier.

Because the investigation layer had a clean interface — records in and a validated dictionary out — the provider could be replaced without changing the rest of the reconciliation pipeline.

---

### Incorrect model names

I initially guessed model names that were not available on my account and received 404 errors.

Instead of continuing to guess, I queried the available models and used the exact model identifier returned for the account.

The investigator currently uses:

```text
openai/gpt-oss-20b
```

through Groq's API.

---

### Dashboard rendering issue

The dashboard originally relied on native Streamlit charts and tables with theme configuration.

The styling did not behave as expected.

Rather than spending more time debugging framework defaults, I rebuilt the relevant visualizations using Plotly and HTML, with the required styling explicitly defined.

---

### Dashboard showing incorrect human escalations

One of the most important bugs occurred when the reconciliation engine correctly detected a human escalation, but the dashboard displayed zero.

The reconciliation logic was correct.

The problem was in the dashboard parser.

It was looking for a nested JSON structure that the generated reconciliation report did not actually use.

Because the lookup failed silently, the dashboard fell back to displaying zero escalations.

I found the issue by comparing the dashboard output directly against the terminal output and the generated JSON for the same run.

I then fixed the parser and validated the dashboard against the actual source output.

This was probably the most useful engineering lesson from the project:

> **A number that looks reasonable isn't necessarily a correct number.**

The entire pipeline has to agree with the underlying source data.

---

## Architecture

At a high level, Recon contains five main stages:

```text
1. Data ingestion
        |
        v
2. Deterministic reconciliation
        |
        v
3. Exception classification
        |
        v
4. AI investigation
        |
        v
5. Confidence routing + audit output
```

### Data ingestion

The application reads:

```text
internal_ledger.csv
bank_statement.csv
```

The synthetic data generator also creates:

```text
ground_truth.csv
```

The ground truth is used only for evaluation.

It is not used by the reconciliation engine when making predictions.

---

### Reconciliation engine

The deterministic engine attempts to match records using rules and similarity checks.

The output contains the matching result and relevant evidence used to explain the decision.

---

### AI investigator

Only residual ambiguous cases are passed to the LLM.

The investigator returns structured information rather than free-form text alone.

---

### Confidence routing

The application checks the returned confidence score.

```text
confidence >= 0.85
        |
        v
    auto-resolve

confidence < 0.85
        |
        v
   human review
```

---

### Audit output

The reconciliation process produces a JSON report containing the decisions and investigation results.

This output is then consumed by the dashboard.

---

## Tech stack

### Core

* Python
* Pandas

### AI

* Groq API
* `openai/gpt-oss-20b`

### Dashboard

* Streamlit
* Plotly
* HTML

### Data

* CSV
* JSON
* Synthetic data generator

### Development

* Git
* GitHub

---

## Project structure

```text
recon/
│
├── data/
│   ├── bank_statement.csv
│   ├── ground_truth.csv
│   ├── internal_ledger.csv
│   └── reconciliation_report.json
│
├── src/
│   ├── generate_data.py
│   ├── reconcile.py
│   ├── llm_investigator.py
│   ├── investigate.py
│   └── dashboard.py
│
├── requirements.txt
└── README.md
```

---

## Running the project

Clone the repository:

```bash
git clone https://github.com/khindimegha-hub/recon.git
cd recon
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate the synthetic data:

```bash
python src/generate_data.py
```

Run deterministic reconciliation:

```bash
python src/reconcile.py
```

Run the full reconciliation and AI investigation pipeline:

```bash
python src/investigate.py
```

Start the dashboard:

```bash
streamlit run src/dashboard.py
```

---

## Groq API key

The AI investigation step uses a Groq API key.

### Windows PowerShell

```powershell
$env:GROQ_API_KEY="your-key-here"
```

### macOS / Linux

```bash
export GROQ_API_KEY="your-key-here"
```

Then run:

```bash
python src/investigate.py
```

If no API key is available, the system does not crash.

Ambiguous cases fall back to:

```text
Needs manual review
```

This follows the same safety principle used when an AI response fails validation or cannot be trusted.

---

## Evaluation methodology

The synthetic data generator creates both the financial records and the expected answers.

The workflow is:

```text
Synthetic data generation
        |
        +----> Ledger
        |
        +----> Bank statement
        |
        +----> Ground truth
                  |
                  v
          Reconciliation engine
                  |
                  v
             Predictions
                  |
                  v
        Compare predictions
        against ground truth
                  |
                  v
             Metrics
```

The reconciliation engine does not read the ground-truth file while making decisions.

This keeps the evaluation separate from the prediction process.

---

## Design principles

Recon follows a few principles throughout the system.

### 1. Don't use AI unnecessarily

If deterministic logic can prove the answer, use deterministic logic.

### 2. Make AI outputs structured

The LLM returns structured information that can be validated before being used.

### 3. Treat uncertainty explicitly

Low-confidence AI results are not forced into an automatic decision.

### 4. Keep financial actions outside the LLM

The model investigates and recommends.

It does not perform financial operations.

### 5. Measure instead of assuming

The system is evaluated against generated ground truth instead of relying only on example matches.

### 6. Keep an audit trail

The reconciliation output is stored as structured JSON so that decisions can be inspected later.

---

## Future improvements

If this were taken beyond the prototype, the next improvements I would make are:

* Add merchant-level historical context to the AI investigator
* Add fee and settlement-rule knowledge
* Replace first-valid fuzzy matching with global optimal matching
* Calibrate the confidence threshold using labeled outcomes
* Add a comprehensive automated test suite
* Add larger and more varied datasets
* Add monitoring for AI confidence and escalation rates
* Add human feedback loops for improving exception classification
* Add production-grade database storage
* Add authentication and role-based access for finance users

---

## Key takeaway

Recon is not built around the idea that an LLM should solve every reconciliation problem.

It is built around deciding **where AI is actually useful**.

Clear cases should be handled by deterministic software.

Ambiguous cases can benefit from AI-assisted investigation.

And uncertain cases should remain under human control.

The principle is simple:

> **Automate what can be proven.**
>
> **Use AI where judgment is useful.**
>
> **Keep humans in control when uncertainty remains.**

---

## Repository

GitHub:

[https://github.com/khindimegha-hub/recon](https://github.com/khindimegha-hub/recon)

```
```
