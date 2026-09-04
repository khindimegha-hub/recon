"""
Reconciliation engine: matches internal_ledger.csv against bank_statement.csv.

Pipeline
--------
Layer 1: Exact ID matching
    Match records using txn_id.

Layer 2: Fuzzy matching
    For records without a txn_id match, match using:
        - merchant
        - amount within tolerance
        - date within tolerance

Layer 3: Deterministic classification
    Explain known discrepancies using auditable rules.

Layer 4: Evaluation
    Compare predictions against the synthetic ground-truth answer key.
    The ground truth is NEVER used during reconciliation itself.

Important
---------
The reconciliation algorithm does NOT read ground_truth.csv while making
predictions. The ground truth is loaded only AFTER classification so that
it can be used to evaluate the result.

AI investigation is handled separately by investigate.py.
"""

import time

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

AMOUNT_TOLERANCE = 2.0
DATE_TOLERANCE_DAYS = 2

AMOUNT_RULE_TOLERANCE = 2.0
DATE_RULE_TOLERANCE_DAYS = 2


# ============================================================
# DATA LOADING
# ============================================================

def load_data(
    ledger_path="data/internal_ledger.csv",
    statement_path="data/bank_statement.csv",
):
    """
    Load internal ledger and bank statement CSV files.

    Returns
    -------
    ledger : pd.DataFrame
    statement : pd.DataFrame
    """

    ledger = pd.read_csv(
        ledger_path,
        parse_dates=["date"],
    )

    statement = pd.read_csv(
        statement_path,
        parse_dates=["date"],
    )

    required_columns = {"txn_id", "merchant", "amount", "date"}

    missing_ledger = required_columns - set(ledger.columns)
    missing_statement = required_columns - set(statement.columns)

    if missing_ledger:
        raise ValueError(
            f"Ledger is missing required columns: {sorted(missing_ledger)}"
        )

    if missing_statement:
        raise ValueError(
            f"Bank statement is missing required columns: "
            f"{sorted(missing_statement)}"
        )

    return ledger, statement


# ============================================================
# LAYER 1 — EXACT ID MATCHING
# ============================================================

def exact_match(ledger, statement):
    """
    Match ledger and statement records using txn_id.

    Returns
    -------
    clean
        Records where txn_id, amount and date all agree.

    near
        Records where txn_id matches but amount/date differs.

    unmatched_ledger
        Ledger records with no matching txn_id.

    unmatched_statement
        Statement records with no matching txn_id.
    """

    common_ids = set(ledger["txn_id"]) & set(statement["txn_id"])

    matched_ledger = ledger[
        ledger["txn_id"].isin(common_ids)
    ].copy()

    matched_statement = statement[
        statement["txn_id"].isin(common_ids)
    ].copy()

    merged = matched_ledger.merge(
        matched_statement,
        on="txn_id",
        suffixes=("_ledger", "_statement"),
    )

    # --------------------------------------------------------
    # Clean exact matches
    # --------------------------------------------------------

    clean = merged[
        (merged["amount_ledger"] == merged["amount_statement"])
        & (merged["date_ledger"] == merged["date_statement"])
    ].copy()

    # --------------------------------------------------------
    # Near matches
    # Same ID, but amount or date differs.
    # These are classified by deterministic rules later.
    # --------------------------------------------------------

    near = merged[
        ~merged["txn_id"].isin(clean["txn_id"])
    ].copy()

    # --------------------------------------------------------
    # Completely unmatched records
    # --------------------------------------------------------

    unmatched_ledger = ledger[
        ~ledger["txn_id"].isin(common_ids)
    ].copy()

    unmatched_statement = statement[
        ~statement["txn_id"].isin(common_ids)
    ].copy()

    return (
        clean,
        near,
        unmatched_ledger,
        unmatched_statement,
    )


# ============================================================
# LAYER 2 — FUZZY MATCHING
# ============================================================

def fuzzy_match(unmatched_ledger, unmatched_statement):
    """
    Match records where txn_id is unavailable/different.

    Matching criteria:
        1. Same merchant
        2. Amount difference <= AMOUNT_TOLERANCE
        3. Date difference <= DATE_TOLERANCE_DAYS

    The existing project uses a greedy first-valid-match strategy.
    This is intentionally preserved for deadline safety and because
    the limitation is documented in the project README.

    Returns
    -------
    fuzzy_df
        Successfully fuzzy-matched records.

    remaining_ledger
        Ledger records still unmatched.

    remaining_statement
        Statement records still unmatched.
    """

    fuzzy_matches = []

    used_statement_idx = set()

    for l_idx, l_row in unmatched_ledger.iterrows():

        for s_idx, s_row in unmatched_statement.iterrows():

            if s_idx in used_statement_idx:
                continue

            same_merchant = (
                l_row["merchant"] == s_row["merchant"]
            )

            amount_difference = abs(
                l_row["amount"] - s_row["amount"]
            )

            date_difference = abs(
                (l_row["date"] - s_row["date"]).days
            )

            amount_close = (
                amount_difference <= AMOUNT_TOLERANCE
            )

            date_close = (
                date_difference <= DATE_TOLERANCE_DAYS
            )

            if (
                same_merchant
                and amount_close
                and date_close
            ):

                fuzzy_matches.append(
                    {
                        "ledger_txn_id": l_row["txn_id"],
                        "statement_txn_id": s_row["txn_id"],
                        "amount_ledger": l_row["amount"],
                        "amount_statement": s_row["amount"],
                        "date_ledger": l_row["date"],
                        "date_statement": s_row["date"],
                        "merchant": l_row["merchant"],
                    }
                )

                used_statement_idx.add(s_idx)

                break

    fuzzy_df = pd.DataFrame(fuzzy_matches)

    if fuzzy_df.empty:

        remaining_ledger = unmatched_ledger.copy()
        remaining_statement = unmatched_statement.copy()

        return (
            fuzzy_df,
            remaining_ledger,
            remaining_statement,
        )

    matched_ledger_ids = fuzzy_df[
        "ledger_txn_id"
    ].tolist()

    matched_statement_ids = fuzzy_df[
        "statement_txn_id"
    ].tolist()

    remaining_ledger = unmatched_ledger[
        ~unmatched_ledger["txn_id"].isin(
            matched_ledger_ids
        )
    ].copy()

    remaining_statement = unmatched_statement[
        ~unmatched_statement["txn_id"].isin(
            matched_statement_ids
        )
    ].copy()

    return (
        fuzzy_df,
        remaining_ledger,
        remaining_statement,
    )


# ============================================================
# LAYER 3 — DETERMINISTIC EXCEPTION CLASSIFICATION
# ============================================================

def classify_near_match(row):
    """
    Deterministically classify an ID-matched transaction where
    amount or date differs.

    Possible outputs
    ----------------
    rounding
    date_shift
    amount_mismatch_needs_review
    unclassified_needs_review
    """

    amount_diff = abs(
        row["amount_ledger"] - row["amount_statement"]
    )

    date_diff = abs(
        (row["date_ledger"] - row["date_statement"]).days
    )

    # --------------------------------------------------------
    # Rule 1: Small amount difference, same date
    # --------------------------------------------------------

    if (
        amount_diff > 0
        and date_diff == 0
        and amount_diff <= AMOUNT_RULE_TOLERANCE
    ):
        return "rounding"

    # --------------------------------------------------------
    # Rule 2: Same amount, small date difference
    # --------------------------------------------------------

    if (
        date_diff > 0
        and amount_diff == 0
        and date_diff <= DATE_RULE_TOLERANCE_DAYS
    ):
        return "date_shift"

    # --------------------------------------------------------
    # Rule 3: Material amount mismatch
    # Send to AI investigation.
    # --------------------------------------------------------

    if amount_diff > AMOUNT_RULE_TOLERANCE:
        return "amount_mismatch_needs_review"

    # --------------------------------------------------------
    # Anything else is not safely explainable.
    # --------------------------------------------------------

    return "unclassified_needs_review"


def classify_unmatched(row, side):
    """
    Classify records that have no counterpart txn_id.

    Current synthetic dataset marks duplicate statement records
    using the _DUP suffix.

    Parameters
    ----------
    row : pd.Series
        Transaction record.

    side : str
        Either 'ledger' or 'statement'.
    """

    txn_id = str(row["txn_id"])

    if txn_id.endswith("_DUP"):
        return "duplicate_in_statement"

    if side == "ledger":
        return "missing_in_statement"

    return "missing_in_ledger"


# ============================================================
# GROUND-TRUTH EVALUATION
# ============================================================

def score_against_ground_truth(
    classified_df,
    ground_truth_path="data/ground_truth.csv",
):
    """
    Evaluate predictions against the synthetic ground truth.

    IMPORTANT:
        This function is called AFTER reconciliation/classification.
        Ground truth is NOT used to make predictions.

    A *_needs_review prediction is considered correct when the actual
    ground-truth label is ambiguous_amount because escalating an
    ambiguous transaction is the intended safe behavior.
    """

    if classified_df.empty:
        return None

    try:
        truth = pd.read_csv(
            ground_truth_path
        ).set_index("txn_id")["true_label"]

    except FileNotFoundError:
        print(
            "Warning: ground_truth.csv not found. "
            "Skipping accuracy evaluation."
        )
        return None

    merged = classified_df.set_index(
        "txn_id"
    ).join(
        truth,
        how="inner",
    )

    if merged.empty:
        return None

    def is_correct(row):
        predicted = str(row["predicted_label"])
        actual = str(row["true_label"])

        # Exact label match
        if predicted == actual:
            return True

        # Safe escalation of genuinely ambiguous cases
        if (
            predicted.endswith("_needs_review")
            and actual == "ambiguous_amount"
        ):
            return True

        return False

    correct = int(
        merged.apply(
            is_correct,
            axis=1,
        ).sum()
    )

    total = len(merged)

    accuracy = (
        correct / total * 100
        if total > 0
        else 0.0
    )

    return {
        "total_scored": total,
        "correct": correct,
        "accuracy_pct": round(
            accuracy,
            1,
        ),
    }


# ============================================================
# METRIC HELPERS
# ============================================================

def calculate_automation_rate(classified_df):
    """
    Calculate the percentage of classified reconciliation items
    that do not require human review or LLM investigation.

    A record is considered automated when its classification does
    NOT end with '_needs_review'.

    This metric is intentionally separate from match rate.

    Returns
    -------
    float
        Automation percentage.
    """

    if classified_df.empty:
        return 0.0

    review_mask = (
        classified_df["predicted_label"]
        .astype(str)
        .str.endswith("_needs_review")
    )

    automated_items = (
        len(classified_df)
        - int(review_mask.sum())
    )

    return (
        automated_items
        / len(classified_df)
        * 100
    )


def calculate_match_rate(
    matched_count,
    total,
):
    """
    Calculate the reconciliation match rate.
    """

    if total <= 0:
        return 0.0

    return (
        matched_count
        / total
        * 100
    )


# ============================================================
# MAIN RECONCILIATION PIPELINE
# ============================================================

def run_reconciliation(
    ledger_path="data/internal_ledger.csv",
    statement_path="data/bank_statement.csv",
    ground_truth_path="data/ground_truth.csv",
):
    """
    Run the complete deterministic reconciliation pipeline.

    Pipeline
    --------
    1. Load data
    2. Exact ID matching
    3. Fuzzy matching
    4. Deterministic exception classification
    5. Ground-truth evaluation
    6. Calculate automation and throughput metrics

    Returns
    -------
    dict
        Complete reconciliation result.
    """

    start_time = time.perf_counter()

    # ========================================================
    # STEP 1 — LOAD DATA
    # ========================================================

    ledger, statement = load_data(
        ledger_path=ledger_path,
        statement_path=statement_path,
    )

    total = len(ledger)

    # ========================================================
    # STEP 2 — EXACT MATCH
    # ========================================================

    (
        clean,
        near,
        unmatched_ledger,
        unmatched_statement,
    ) = exact_match(
        ledger,
        statement,
    )

    # ========================================================
    # STEP 3 — FUZZY MATCH
    # ========================================================

    (
        fuzzy_df,
        remaining_ledger,
        remaining_statement,
    ) = fuzzy_match(
        unmatched_ledger,
        unmatched_statement,
    )

    # ========================================================
    # MATCHING METRICS
    # ========================================================

    matched_count = (
        len(clean)
        + len(near)
        + len(fuzzy_df)
    )

    exception_count = (
        len(remaining_ledger)
        + len(remaining_statement)
    )

    match_rate = calculate_match_rate(
        matched_count,
        total,
    )

    # ========================================================
    # STEP 4 — DETERMINISTIC CLASSIFICATION
    # ========================================================

    classified_rows = []

    # --------------------------------------------------------
    # Near matches
    # --------------------------------------------------------

    for _, row in near.iterrows():

        classified_rows.append(
            {
                "txn_id": row["txn_id"],
                "predicted_label": classify_near_match(row),
            }
        )

    # --------------------------------------------------------
    # Remaining ledger records
    # --------------------------------------------------------

    for _, row in remaining_ledger.iterrows():

        classified_rows.append(
            {
                "txn_id": row["txn_id"],
                "predicted_label": classify_unmatched(
                    row,
                    "ledger",
                ),
            }
        )

    # --------------------------------------------------------
    # Remaining statement records
    # --------------------------------------------------------

    for _, row in remaining_statement.iterrows():

        classified_rows.append(
            {
                "txn_id": row["txn_id"],
                "predicted_label": classify_unmatched(
                    row,
                    "statement",
                ),
            }
        )

    # --------------------------------------------------------
    # Clean exact matches
    # --------------------------------------------------------

    for _, row in clean.iterrows():

        classified_rows.append(
            {
                "txn_id": row["txn_id"],
                "predicted_label": "clean",
            }
        )

    classified_df = pd.DataFrame(
        classified_rows,
        columns=[
            "txn_id",
            "predicted_label",
        ],
    )

    # ========================================================
    # STEP 5 — IDENTIFY AI-ELIGIBLE CASES
    # ========================================================

    if not classified_df.empty:

        needs_llm = classified_df[
            classified_df[
                "predicted_label"
            ]
            .astype(str)
            .str.endswith("_needs_review")
        ].copy()

    else:

        needs_llm = pd.DataFrame(
            columns=[
                "txn_id",
                "predicted_label",
            ]
        )

    # ========================================================
    # STEP 6 — GROUND-TRUTH EVALUATION
    # ========================================================

    scoring = score_against_ground_truth(
        classified_df,
        ground_truth_path=ground_truth_path,
    )

    # ========================================================
    # STEP 7 — AUTOMATION RATE
    # ========================================================

    automation_rate = calculate_automation_rate(
        classified_df
    )

    # ========================================================
    # STEP 8 — THROUGHPUT
    # ========================================================

    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    throughput = (
        total / elapsed_seconds
        if elapsed_seconds > 0
        else float("inf")
    )

    # ========================================================
    # CONSOLE REPORT
    # ========================================================

    print()
    print("=" * 60)
    print("             RECONCILIATION REPORT")
    print("=" * 60)

    print()
    print("--- Matching ---")

    print(
        f"Total ledger transactions:      {total}"
    )

    print(
        f"Clean exact matches:             {len(clean)}"
    )

    print(
        f"Near matches (ID matched,        "
        f"amount/date differ):            {len(near)}"
    )

    print(
        f"Fuzzy matches (no ID,            "
        f"amount + date matched):         {len(fuzzy_df)}"
    )

    print(
        f"Unresolved exceptions:           "
        f"{exception_count}"
    )

    print(
        f"Match rate:                      "
        f"{match_rate:.1f}%"
    )

    print()
    print("--- Rule-based classification ---")

    if not classified_df.empty:

        print(
            classified_df[
                "predicted_label"
            ]
            .value_counts()
            .to_string()
        )

    else:

        print("No classifications generated.")

    print()
    print("--- AI routing ---")

    print(
        f"Sent to LLM (ambiguous only):    "
        f"{len(needs_llm)}"
    )

    print(
        f"Deterministic automation rate:   "
        f"{automation_rate:.1f}%"
    )

    # ========================================================
    # ACCURACY
    # ========================================================

    if scoring:

        print()
        print("--- Accuracy vs. ground truth ---")

        print(
            f"Scored: {scoring['total_scored']} | "
            f"Correct: {scoring['correct']} | "
            f"Accuracy: {scoring['accuracy_pct']}%"
        )

    # ========================================================
    # THROUGHPUT
    # ========================================================

    print()
    print("--- Throughput ---")

    print(
        f"Processed {total} transactions in "
        f"{elapsed_seconds * 1000:.1f}ms "
        f"({throughput:.0f} transactions/sec, "
        f"deterministic layer only)"
    )

    print()
    print("=" * 60)

    # ========================================================
    # RETURN COMPLETE RESULT
    # ========================================================

    return {
        # Raw matching outputs
        "clean": clean,
        "near": near,
        "fuzzy": fuzzy_df,

        # Unmatched outputs
        "unmatched_ledger": remaining_ledger,
        "unmatched_statement": remaining_statement,

        # Classification
        "classified": classified_df,
        "needs_llm": needs_llm,

        # Evaluation
        "scoring": scoring,

        # Metrics
        "total": total,
        "matched_count": matched_count,
        "exception_count": exception_count,
        "match_rate": match_rate,
        "automation_rate": automation_rate,

        # Performance
        "throughput": {
            "total": total,
            "elapsed_seconds": elapsed_seconds,
            "txn_per_sec": throughput,
        },
    }


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_reconciliation()