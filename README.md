# 🖥️ Dashboard

Recon includes a Streamlit dashboard for finance-controller-style monitoring.

![Recon Dashboard](dashboard.png)

The dashboard provides:

### Executive KPIs

- Total transactions
- Matched transactions
- Exceptions flagged
- Match rate
- Deterministic automation
- AI investigations
- AI auto-resolutions
- Human escalations

### Validation

- Ground-truth accuracy
- Correct predictions
- Scored items

### Loop Closure

Shows how the entire exception workflow was resolved:

```text
74 classified items
        │
        ├── 67 deterministic
        ├── 6 AI auto-resolved
        └── 1 human escalation
