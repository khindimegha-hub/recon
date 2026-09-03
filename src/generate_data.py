"""
Generates two synthetic transaction datasets simulating:
- internal_ledger.csv: what our system recorded
- bank_statement.csv: what the bank/PG actually shows

Deliberately injects realistic mismatches so the reconciliation
engine has genuine exceptions to resolve, not just clean matches.
"""

import pandas as pd
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible output

NUM_TRANSACTIONS = 70
START_DATE = datetime(2026, 8, 1)

def generate_base_transactions(n):
    transactions = []
    for i in range(n):
        txn_id = f"TXN{1000 + i}"
        amount = round(random.uniform(150, 25000), 2)
        date = START_DATE + timedelta(days=random.randint(0, 30))
        merchant = random.choice(
            ["Zomato", "Swiggy", "Amazon", "Flipkart", "Myntra", "BigBasket", "Ola", "Uber"]
        )
        transactions.append(
            {"txn_id": txn_id, "amount": amount, "date": date, "merchant": merchant}
        )
    return transactions


def build_with_ground_truth(base_transactions):
    """
    Builds the ledger and statement datasets, and also records the
    TRUE mismatch_type per transaction. This answer key is what lets
    us later measure real accuracy instead of guessing.
    """
    ledger_rows, statement_rows, ground_truth_rows = [], [], []

    for txn in base_transactions:
        mismatch_type = random.choices(
            ["clean", "rounding", "date_shift", "missing_in_statement",
             "missing_in_ledger", "duplicate_in_statement"],
            weights=[55, 15, 12, 8, 6, 4],
            k=1,
        )[0]

        ledger_row = {
            "txn_id": txn["txn_id"], "amount": txn["amount"],
            "date": txn["date"].strftime("%Y-%m-%d"), "merchant": txn["merchant"],
        }
        statement_row = dict(ledger_row)
        ground_truth_rows.append({"txn_id": txn["txn_id"], "true_label": mismatch_type})

        if mismatch_type == "clean":
            ledger_rows.append(ledger_row)
            statement_rows.append(statement_row)
        elif mismatch_type == "rounding":
            statement_row["amount"] = round(txn["amount"] - random.uniform(0.5, 2.0), 2)
            ledger_rows.append(ledger_row)
            statement_rows.append(statement_row)
        elif mismatch_type == "date_shift":
            shifted_date = txn["date"] + timedelta(days=random.choice([1, 2]))
            statement_row["date"] = shifted_date.strftime("%Y-%m-%d")
            ledger_rows.append(ledger_row)
            statement_rows.append(statement_row)
        elif mismatch_type == "missing_in_statement":
            ledger_rows.append(ledger_row)
        elif mismatch_type == "missing_in_ledger":
            statement_rows.append(statement_row)
        elif mismatch_type == "duplicate_in_statement":
            ledger_rows.append(ledger_row)
            statement_rows.append(statement_row)
            dup_row = dict(statement_row)
            dup_row["txn_id"] = txn["txn_id"] + "_DUP"
            statement_rows.append(dup_row)
            ground_truth_rows.append({"txn_id": txn["txn_id"] + "_DUP", "true_label": "duplicate_in_statement"})

    return (
        pd.DataFrame(ledger_rows),
        pd.DataFrame(statement_rows),
        pd.DataFrame(ground_truth_rows),
    )


if __name__ == "__main__":
    base = generate_base_transactions(NUM_TRANSACTIONS)
    ledger_df, statement_df, ground_truth_df = build_with_ground_truth(base)

    ledger_df.to_csv("data/internal_ledger.csv", index=False)
    statement_df.to_csv("data/bank_statement.csv", index=False)
    ground_truth_df.to_csv("data/ground_truth.csv", index=False)

    print(f"internal_ledger.csv: {len(ledger_df)} rows")
    print(f"bank_statement.csv:  {len(statement_df)} rows")
    print(f"ground_truth.csv:    {len(ground_truth_df)} rows (answer key)")
    print("Data generated successfully.")