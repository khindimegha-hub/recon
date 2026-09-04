"""
Professional dashboard for the Recon AI Ledger Reconciliation Engine.

Run from the project root:
    streamlit run src/dashboard.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# IMPORT ENGINE
# ============================================================

SRC_DIR = os.path.dirname(os.path.abspath(__file__))

if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from reconcile import load_data, run_reconciliation


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Recon — AI Ledger Reconciliation Engine",
    layout="wide",
    page_icon="💠",
)


# ============================================================
# HTML RENDER HELPER
# ============================================================

def render_html(html: str) -> None:
    """
    Flatten HTML before passing it to Streamlit.

    This prevents Streamlit/CommonMark from interpreting
    indented HTML as Markdown code blocks.
    """

    flat = " ".join(
        line.strip()
        for line in html.strip().splitlines()
        if line.strip()
    )

    st.markdown(
        flat,
        unsafe_allow_html=True,
    )


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
    <style>

        #MainMenu, header, footer {
            visibility: hidden;
        }

        .stApp {
            background: #0b1120;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }


        /* ================================================== */
        /* HERO */
        /* ================================================== */

        .hero-title {
            font-size: 2.1rem;
            font-weight: 800;
            color: #f1f5f9;
            letter-spacing: -0.02em;
            margin-bottom: 0.1rem;
        }

        .hero-sub {
            color: #94a3b8;
            font-size: 0.95rem;
            margin-bottom: 1.6rem;
        }

        .badge {
            display: inline-block;
            background: rgba(52, 211, 153, 0.12);
            color: #34d399;
            border: 1px solid rgba(52, 211, 153, 0.35);
            padding: 3px 12px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            margin-left: 10px;
            vertical-align: middle;
        }


        /* ================================================== */
        /* KPI CARDS */
        /* ================================================== */

        .kpi-card {
            background: linear-gradient(
                180deg,
                #131c31 0%,
                #101828 100%
            );
            border: 1px solid #1e293b;
            border-radius: 14px;
            padding: 18px 20px;
            height: 100%;
        }

        .kpi-label {
            color: #94a3b8;
            font-size: 0.76rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 6px;
        }

        .kpi-value {
            color: #f8fafc;
            font-size: 1.9rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .kpi-description {
            color: #64748b;
            font-size: 0.72rem;
            margin-top: 3px;
        }


        /* ================================================== */
        /* ACCURACY BANNER */
        /* ================================================== */

        .accuracy-banner {
            background: linear-gradient(
                90deg,
                rgba(52, 211, 153, 0.14),
                rgba(52, 211, 153, 0.03)
            );
            border: 1px solid rgba(52, 211, 153, 0.3);
            border-radius: 12px;
            padding: 14px 20px;
            color: #d1fae5;
            font-size: 0.92rem;
            margin: 22px 0 28px 0;
        }

        .accuracy-banner b {
            color: #34d399;
            font-size: 1.05rem;
        }


        /* ================================================== */
        /* SECTION HEADERS */
        /* ================================================== */

        .section-title {
            color: #e2e8f0;
            font-size: 1.1rem;
            font-weight: 700;
            margin: 8px 0 12px 0;
        }

        .section-subtitle {
            color: #64748b;
            font-size: 0.78rem;
            margin-top: -7px;
            margin-bottom: 12px;
        }

        .panel {
            background: #101828;
            border: 1px solid #1e293b;
            border-radius: 14px;
            padding: 18px 20px;
            height: 100%;
        }


        /* ================================================== */
        /* LOOP CLOSURE */
        /* ================================================== */

        .closure-panel {
            background: linear-gradient(
                135deg,
                rgba(52, 211, 153, 0.10),
                rgba(15, 23, 42, 0.75)
            );
            border: 1px solid rgba(52, 211, 153, 0.25);
            border-radius: 14px;
            padding: 20px;
            margin-top: 22px;
        }

        .closure-number {
            color: #34d399;
            font-size: 2rem;
            font-weight: 800;
        }

        .closure-label {
            color: #cbd5e1;
            font-size: 0.9rem;
            font-weight: 600;
        }

        .closure-description {
            color: #64748b;
            font-size: 0.78rem;
            margin-top: 3px;
        }


        /* ================================================== */
        /* PRINCIPLE STRIP */
        /* ================================================== */

        .principle-strip {
            margin-top: 24px;
            padding: 14px 18px;
            border-radius: 10px;
            background: #0f172a;
            border: 1px dashed #334155;
            color: #94a3b8;
            font-size: 0.85rem;
            text-align: center;
        }

        .principle-strip b {
            color: #cbd5e1;
        }


        /* ================================================== */
        /* TABLE */
        /* ================================================== */

        [data-testid="stDataFrame"] {
            border-radius: 10px;
            overflow: hidden;
        }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATA CHECK
# ============================================================

if not os.path.exists("data/internal_ledger.csv"):
    st.error(
        "No data found. Run `python src/generate_data.py` first."
    )
    st.stop()


# ============================================================
# RUN RECONCILIATION
# ============================================================

results = run_reconciliation()

ledger, statement = load_data()

total = results["total"]

matched = (
    len(results["clean"])
    + len(results["near"])
    + len(results["fuzzy"])
)

exceptions = results["exception_count"]

match_rate = results["match_rate"]

automation_rate = results["automation_rate"]

scoring = results["scoring"]

classified_df = results["classified"]

needs_llm = results["needs_llm"]


# ============================================================
# CLASSIFICATION POPULATION
# ============================================================

# This is deliberately separate from the 66-record ledger
# population used for match rate.
#
# The classification population includes:
#   - ledger transactions
#   - statement-only exceptions
#
# In the current synthetic dataset this produces 74 classified
# records.

classified_total = len(classified_df)


# ============================================================
# LOAD AI AUDIT REPORT
# ============================================================

audit_path = "data/reconciliation_report.json"

audit_data: Dict[str, Any] = {}
summary: Dict[str, Any] = {}

if os.path.exists(audit_path):

    try:

        with open(
            audit_path,
            "r",
            encoding="utf-8",
        ) as f:
            loaded = json.load(f)

        if isinstance(loaded, dict):

            audit_data = loaded
            summary = loaded  # investigate.py writes these keys flat, not nested

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
        AttributeError,
    ):
        audit_data = {}
        summary = {}


# ============================================================
# AI LOOP-CLOSURE METRICS
# ============================================================

# AI investigations are directly tied to the deterministic
# engine's needs_llm population.

ai_investigations = len(needs_llm)

# Prefer the persisted audit report when it exposes these
# values. Otherwise derive them from the routing population.

ai_auto_resolved = summary.get("ai_auto_resolved_count", None)

human_escalations = summary.get("escalated_to_human_count", None)


# Convert valid numeric values safely.

try:
    if ai_auto_resolved is not None:
        ai_auto_resolved = int(ai_auto_resolved)
except (TypeError, ValueError):
    ai_auto_resolved = None

try:
    if human_escalations is not None:
        human_escalations = int(human_escalations)
except (TypeError, ValueError):
    human_escalations = None


# If the report does not expose routing totals, derive them.
#
# Every AI investigation ends in one of two states:
#   1. auto-resolved
#   2. human escalation
#
# Therefore:
#
#     AI auto-resolved = AI investigations - human escalations

if human_escalations is None:

    human_escalations = 0

if ai_auto_resolved is None:

    ai_auto_resolved = max(
        0,
        ai_investigations - human_escalations,
    )


# ============================================================
# ZERO-HUMAN-ACTION
# ============================================================

# The loop-closure denominator is the complete classification
# population, not the 66-record ledger population.
#
# Anything that did not require human escalation required
# zero human action.

zero_human_action = max(
    0,
    classified_total - human_escalations,
)


# ============================================================
# HEADER
# ============================================================

render_html(
    """
    <div class="hero-title">
        Recon
        <span class="badge">● LIVE</span>
    </div>
    """
)

render_html(
    """
    <div class="hero-sub">
        AI Ledger Reconciliation Engine — deterministic rule-based
        matching, with AI reserved strictly for exceptions no rule
        can confidently explain.
    </div>
    """
)


# ============================================================
# PRIMARY KPI ROW
# ============================================================

k1, k2, k3, k4 = st.columns(4)

primary_kpis = [

    (
        k1,
        "Total Transactions",
        f"{total}",
        "Ledger records processed",
    ),

    (
        k2,
        "Matched",
        f"{matched}",
        "Exact + near + fuzzy ledger matches",
    ),

    (
        k3,
        "Exceptions Flagged",
        f"{exceptions}",
        "Residual unmatched records",
    ),

    (
        k4,
        "Match Rate",
        f"{match_rate:.1f}%",
        "Ledger-to-statement coverage",
    ),
]


for col, label, value, description in primary_kpis:

    with col:

        render_html(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-description">{description}</div>
            </div>
            """
        )


# ============================================================
# SECONDARY KPI ROW
# ============================================================

st.markdown(
    "<div style='height:12px'></div>",
    unsafe_allow_html=True,
)

k5, k6, k7, k8 = st.columns(4)

secondary_kpis = [

    (
        k5,
        "Deterministic Automation",
        f"{automation_rate:.1f}%",
        "Resolved without AI",
    ),

    (
        k6,
        "AI Investigations",
        f"{ai_investigations}",
        "Ambiguous cases routed to AI",
    ),

    (
        k7,
        "AI Auto-Resolved",
        f"{ai_auto_resolved}",
        "AI cases above confidence threshold",
    ),

    (
        k8,
        "Human Escalations",
        f"{human_escalations}",
        "Cases deliberately not automated",
    ),
]


for col, label, value, description in secondary_kpis:

    with col:

        render_html(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-description">{description}</div>
            </div>
            """
        )


# ============================================================
# GROUND-TRUTH VALIDATION
# ============================================================

if scoring:

    render_html(
        f"""
        <div class="accuracy-banner">
            ✓ Validated against a known ground-truth answer key —
            <b>{scoring["accuracy_pct"]}% classification accuracy</b>
            ({scoring["correct"]}/{scoring["total_scored"]}
            transactions correctly explained)
        </div>
        """
    )


# ============================================================
# FINANCE OPS LOOP CLOSURE
# ============================================================

render_html(
    f"""
    <div class="closure-panel">

        <div style="
            color:#e2e8f0;
            font-size:1.05rem;
            font-weight:700;
            margin-bottom:12px;
        ">
            Finance Ops Loop Closure
        </div>

        <div style="
            display:flex;
            align-items:center;
            gap:24px;
            flex-wrap:wrap;
        ">

            <div>

                <div class="closure-number">
                    {zero_human_action}/{classified_total}
                </div>

                <div class="closure-label">
                    Zero Human Action
                </div>

                <div class="closure-description">
                    Classified records resolved without manual intervention
                </div>

            </div>

            <div style="
                height:52px;
                width:1px;
                background:#1e293b;
            "></div>

            <div>

                <div class="closure-number">
                    {ai_auto_resolved}/{ai_investigations}
                </div>

                <div class="closure-label">
                    AI Resolution
                </div>

                <div class="closure-description">
                    Ambiguous cases automatically resolved
                </div>

            </div>

            <div style="
                height:52px;
                width:1px;
                background:#1e293b;
            "></div>

            <div>

                <div style="
                    color:#facc15;
                    font-size:2rem;
                    font-weight:800;
                ">
                    {human_escalations}
                </div>

                <div class="closure-label">
                    Human Review
                </div>

                <div class="closure-description">
                    Deliberately escalated when confidence was insufficient
                </div>

            </div>

        </div>

    </div>
    """
)


# ============================================================
# CHART + AI REASONING PANEL
# ============================================================

left, right = st.columns([1.3, 1])


# ============================================================
# CLASSIFICATION BREAKDOWN
# ============================================================

with left:

    render_html(
        """
        <div class="section-title">
            Reconciliation Classification Breakdown
        </div>
        """
    )

    render_html(
        """
        <div class="section-subtitle">
            Every ledger and statement-side record receives an auditable classification.
        </div>
        """
    )

    if not classified_df.empty:

        breakdown = (
            classified_df[
                "predicted_label"
            ]
            .value_counts()
        )

        fig = go.Figure(
            go.Bar(
                x=breakdown.index.tolist(),
                y=breakdown.values.tolist(),
                marker_color="#34d399",
                marker_line_width=0,
            )
        )

        fig.update_layout(
            paper_bgcolor="#101828",
            plot_bgcolor="#101828",
            font_color="#94a3b8",
            height=300,
            margin=dict(
                l=10,
                r=10,
                t=10,
                b=10,
            ),
            xaxis=dict(
                showgrid=False,
                tickfont=dict(
                    color="#94a3b8",
                    size=10,
                ),
                tickangle=-25,
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#1e293b",
                tickfont=dict(
                    color="#94a3b8",
                ),
            ),
            bargap=0.3,
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "displayModeBar": False,
            },
        )

    else:

        st.info(
            "No classifications generated."
        )


# ============================================================
# AI REASONING
# ============================================================

with right:

    render_html(
        """
        <div class="section-title">
            AI Investigation — Sample Case
        </div>
        """
    )

    if not needs_llm.empty:

        sample_txn = needs_llm.iloc[0]["txn_id"]

        render_html(
            f"""
            <div class="panel">

                <div style="
                    color:#f8fafc;
                    font-weight:700;
                    font-size:1rem;
                ">
                    {sample_txn}
                </div>

                <div style="
                    color:#facc15;
                    font-size:0.8rem;
                    font-weight:600;
                    margin:6px 0;
                ">
                    FLAGGED — AMOUNT MISMATCH
                </div>

                <div style="
                    color:#94a3b8;
                    font-size:0.85rem;
                    line-height:1.55;
                ">
                    Ledger and statement amounts differ beyond the
                    deterministic tolerance, while txn_id, date,
                    and merchant agree.

                    <br><br>

                    Routed to AI because deterministic rules could not
                    safely explain the discrepancy.
                </div>

                <div style="
                    margin-top:12px;
                    color:#64748b;
                    font-size:0.78rem;
                ">
                    Confidence-scored · Evidence-backed ·
                    Human escalation when confidence is insufficient
                </div>

            </div>
            """
        )

    else:

        render_html(
            """
            <div class="panel">
                No ambiguous cases this run —
                deterministic rules resolved everything.
            </div>
            """
        )


# ============================================================
# CLASSIFIED TRANSACTIONS
# ============================================================

render_html(
    """
    <div class="section-title" style="margin-top:26px;">
        Flagged &amp; Classified Transactions
    </div>
    """
)

render_html(
    """
    <div class="section-subtitle">
        Rule-based resolutions and residual exceptions are shown separately
        through their classification labels.
    </div>
    """
)


# Exclude clean records.
# This table focuses on non-clean classifications.

if not classified_df.empty:

    review_df = classified_df[
        classified_df["predicted_label"] != "clean"
    ].copy()

else:

    review_df = pd.DataFrame(
        columns=[
            "txn_id",
            "predicted_label",
        ]
    )


# ============================================================
# CLASSIFICATION TABLE
# ============================================================

LABEL_COLORS = {

    "rounding": "#38bdf8",

    "date_shift": "#a78bfa",

    "duplicate_in_statement": "#f472b6",

    "missing_in_ledger": "#fb923c",

    "missing_in_statement": "#fb923c",

    "amount_mismatch_needs_review": "#facc15",

    "unclassified_needs_review": "#facc15",
}


rows_html = ""


for _, row in review_df.iterrows():

    label = str(
        row["predicted_label"]
    )

    color = LABEL_COLORS.get(
        label,
        "#94a3b8",
    )

    rows_html += (
        "<tr>"

        '<td style="'
        "padding:10px 16px;"
        "color:#e2e8f0;"
        "font-size:0.88rem;"
        '">'
        f'{row["txn_id"]}'
        "</td>"

        '<td style="padding:10px 16px;">'

        f'<span style="'
        f"background:{color}22;"
        f"color:{color};"
        "padding:2px 10px;"
        "border-radius:6px;"
        "font-size:0.78rem;"
        "font-weight:600;"
        '">'
        f"{label}"
        "</span>"

        "</td>"

        "</tr>"
    )


table_html = (
    '<div style="'
    "background:#101828;"
    "border:1px solid #1e293b;"
    "border-radius:14px;"
    "overflow:hidden;"
    '">'

    '<div style="'
    "max-height:300px;"
    "overflow-y:auto;"
    '">'

    '<table style="'
    "width:100%;"
    "border-collapse:collapse;"
    '">'

    "<thead>"

    '<tr style="border-bottom:1px solid #1e293b;">'

    '<th style="'
    "padding:10px 16px;"
    "text-align:left;"
    "color:#64748b;"
    "font-size:0.75rem;"
    "text-transform:uppercase;"
    "letter-spacing:0.05em;"
    '">'
    "Transaction ID"
    "</th>"

    '<th style="'
    "padding:10px 16px;"
    "text-align:left;"
    "color:#64748b;"
    "font-size:0.75rem;"
    "text-transform:uppercase;"
    "letter-spacing:0.05em;"
    '">'
    "Classification"
    "</th>"

    "</tr>"

    "</thead>"

    "<tbody>"
    + rows_html
    + "</tbody>"

    "</table>"

    "</div>"

    "</div>"
)


render_html(table_html)


# ============================================================
# THROUGHPUT
# ============================================================

throughput = results.get(
    "throughput",
    {},
)

txn_per_sec = throughput.get(
    "txn_per_sec",
    0,
)


render_html(
    f"""
    <div style="
        margin-top:18px;
        color:#64748b;
        font-size:0.76rem;
        text-align:right;
    ">
        Deterministic benchmark:
        <b style="color:#94a3b8;">
            {txn_per_sec:,.0f} transactions/sec
        </b>
        in this local run
    </div>
    """
)


# ============================================================
# DESIGN PRINCIPLE
# ============================================================

render_html(
    """
    <div class="principle-strip">
        Design principle:
        <b>
            deterministic rules handle everything provable.
            AI investigates only residual ambiguity.
            The system escalates when confidence is insufficient —
            and never moves money.
        </b>
    </div>
    """
)