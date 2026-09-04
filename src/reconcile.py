"""
Reconciliation engine: matches internal_ledger.csv against bank_statement.csv.

Layer 1 (exact match): match on txn_id.
Layer 2 (fuzzy match): for unmatched rows, match on merchant + amount
                       within tolerance + date within tolerance.
Anything left after both layers is a genuine exception.
"""

import pandas as pd
import time

AMOUNT_TOLERANCE = 2.0   # rupees
DATE_TOLERANCE_DAYS = 2


def load_data(ledger_path="data/internal_ledger.csv", statement_path="data/bank_statement.csv"):
    ledger = pd.read_csv(ledger_path, parse_dates=["date"])
    statement = pd.read_csv(statement_path, parse_dates=["date"])
    return ledger, statement


def exact_match(ledger, statement):
    """Match on txn_id. Returns matched pairs, and the two unmatched remainders."""
    common_ids = set(ledger["txn_id"]) & set(statement["txn_id"])

    matched_ledger = ledger[ledger["txn_id"].isin(common_ids)].copy()
    matched_statement = statement[statement["txn_id"].isin(common_ids)].copy()

    # Even with matching IDs, amount/date could still differ slightly —
    # those go to fuzzy layer for classification, not treated as clean matches.
    merged = matched_ledger.merge(
        matched_statement, on="txn_id", suffixes=("_ledger", "_statement")
    )
    clean = merged[
        (merged["amount_ledger"] == merged["amount_statement"])
        & (merged["date_ledger"] == merged["date_statement"])
    ]
    near = merged[~merged["txn_id"].isin(clean["txn_id"])]

    unmatched_ledger = ledger[~ledger["txn_id"].isin(common_ids)].copy()
    unmatched_statement = statement[~statement["txn_id"].isin(common_ids)].copy()

    return clean, near, unmatched_ledger, unmatched_statement


def fuzzy_match(unmatched_ledger, unmatched_statement):
    """
    For rows with no txn_id match at all, try matching on merchant + amount
    tolerance + date tolerance. Handles duplicates and logging gaps.
    """
    fuzzy_matches = []
    used_statement_idx = set()

    for l_idx, l_row in unmatched_ledger.iterrows():
        for s_idx, s_row in unmatched_statement.iterrows():
            if s_idx in used_statement_idx:
                continue
            same_merchant = l_row["merchant"] == s_row["merchant"]
            amount_close = abs(l_row["amount"] - s_row["amount"]) <= AMOUNT_TOLERANCE
            date_close = abs((l_row["date"] - s_row["date"]).days) <= DATE_TOLERANCE_DAYS

            if same_merchant and amount_close and date_close:
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
    matched_ledger_ids = fuzzy_df["ledger_txn_id"].tolist() if not fuzzy_df.empty else []
    matched_statement_ids = fuzzy_df["statement_txn_id"].tolist() if not fuzzy_df.empty else []

    remaining_ledger = unmatched_ledger[~unmatched_ledger["txn_id"].isin(matched_ledger_ids)]
    remaining_statement = unmatched_statement[~unmatched_statement["txn_id"].isin(matched_statement_ids)]

    return fuzzy_df, remaining_ledger, remaining_statement


AMOUNT_RULE_TOLERANCE = 2.0
DATE_RULE_TOLERANCE_DAYS = 2


def classify_near_match(row):
    """
    Deterministic rule classification for id-matched rows where amount
    or date differ. This is what replaces 'the AI thinks these match'
    with a named, auditable rule.
    """
    amount_diff = abs(row["amount_ledger"] - row["amount_statement"])
    date_diff = abs((row["date_ledger"] - row["date_statement"]).days)

    if amount_diff > 0 and date_diff == 0 and amount_diff <= AMOUNT_RULE_TOLERANCE:
        return "rounding"
    if date_diff > 0 and amount_diff == 0 and date_diff <= DATE_RULE_TOLERANCE_DAYS:
        return "date_shift"
    if amount_diff > AMOUNT_RULE_TOLERANCE:
        return "amount_mismatch_needs_review"  # ambiguous -> goes to LLM
    return "unclassified_needs_review"


def classify_unmatched(row, side):
    """Rule classification for rows with no counterpart id at all."""
    if row["txn_id"].endswith("_DUP"):
        return "duplicate_in_statement"
    return "missing_in_statement" if side == "ledger" else "missing_in_ledger"


def score_against_ground_truth(classified_df, ground_truth_path="data/ground_truth.csv"):
    """
    Compares the engine's classification against the generator's known
    answer key. A prediction ending in '_needs_review' counts as CORRECT
    when the true label is genuinely ambiguous ('ambiguous_amount') —
    flagging it for review IS the right outcome there, not a miss.
    """
    truth = pd.read_csv(ground_truth_path).set_index("txn_id")["true_label"]
    merged = classified_df.set_index("txn_id").join(truth, how="inner")
    if merged.empty:
        return None

    def is_correct(row):
        if row["predicted_label"] == row["true_label"]:
            return True
        if row["predicted_label"].endswith("_needs_review") and row["true_label"] == "ambiguous_amount":
            return True
        return False

    correct = int(merged.apply(is_correct, axis=1).sum())
    total = len(merged)
    accuracy = correct / total * 100
    return {"total_scored": total, "correct": correct, "accuracy_pct": round(accuracy, 1)}


def run_reconciliation():
    start_time = time.perf_counter()

    ledger, statement = load_data()
    total = len(ledger)

    clean, near, unmatched_ledger, unmatched_statement = exact_match(ledger, statement)
    fuzzy_df, remaining_ledger, remaining_statement = fuzzy_match(unmatched_ledger, unmatched_statement)

    matched_count = len(clean) + len(near) + len(fuzzy_df)
    exception_count = len(remaining_ledger) + len(remaining_statement)

    # --- Rule-based classification (this is the "taxonomy" upgrade) ---
    classified_rows = []
    for _, row in near.iterrows():
        classified_rows.append({"txn_id": row["txn_id"], "predicted_label": classify_near_match(row)})
    for _, row in remaining_ledger.iterrows():
        classified_rows.append({"txn_id": row["txn_id"], "predicted_label": classify_unmatched(row, "ledger")})
    for _, row in remaining_statement.iterrows():
        classified_rows.append({"txn_id": row["txn_id"], "predicted_label": classify_unmatched(row, "statement")})
    for _, row in clean.iterrows():
        classified_rows.append({"txn_id": row["txn_id"], "predicted_label": "clean"})

    classified_df = pd.DataFrame(classified_rows)
    needs_llm = classified_df[classified_df["predicted_label"].str.endswith("_needs_review")]
    scoring = score_against_ground_truth(classified_df)

    elapsed_seconds = time.perf_counter() - start_time
    throughput = total / elapsed_seconds if elapsed_seconds > 0 else float("inf")

    print("=== Reconciliation Report ===")
    print(f"Total ledger transactions:     {total}")
    print(f"Clean exact matches:            {len(clean)}")
    print(f"Near matches (id match,          amount/date differ): {len(near)}")
    print(f"Fuzzy matches (no id,             matched on amount+date): {len(fuzzy_df)}")
    print(f"Unresolved exceptions:          {exception_count}")
    print(f"Match rate:                     {matched_count / total * 100:.1f}%")
    print(f"\n--- Rule-based classification ---")
    print(classified_df["predicted_label"].value_counts().to_string())
    print(f"\nSent to LLM (ambiguous only):    {len(needs_llm)}")
    if scoring:
        print(f"\n--- Accuracy vs. ground truth ---")
        print(f"Scored: {scoring['total_scored']} | Correct: {scoring['correct']} | "
              f"Accuracy: {scoring['accuracy_pct']}%")
    print(f"\n--- Throughput ---")
    print(f"Processed {total} transactions in {elapsed_seconds*1000:.1f}ms "
          f"({throughput:.0f} transactions/sec, deterministic layer only)")

    return {
        "clean": clean, "near": near, "fuzzy": fuzzy_df,
        "unmatched_ledger": remaining_ledger, "unmatched_statement": remaining_statement,
        "classified": classified_df, "needs_llm": needs_llm, "scoring": scoring,
        "throughput": {"total": total, "elapsed_seconds": elapsed_seconds, "txn_per_sec": throughput},
    }


if __name__ == "__main__":
    run_reconciliation()