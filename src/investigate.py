"""
Runs the full reconciliation pipeline, then sends only the genuinely
ambiguous exceptions (needs_llm) to the LLM investigator, one at a time,
and prints a structured result for each.

This is the file that demonstrates the complete story:
  deterministic rules -> named exceptions -> AI only where rules can't decide
"""

import pandas as pd
from reconcile import run_reconciliation, load_data
from llm_investigator import investigate_exception

def get_original_records(txn_id, ledger, statement):
    ledger_match = ledger[ledger["txn_id"] == txn_id]
    statement_match = statement[statement["txn_id"] == txn_id]
    ledger_record = _to_serializable(ledger_match.to_dict("records")[0]) if not ledger_match.empty else None
    statement_record = _to_serializable(statement_match.to_dict("records")[0]) if not statement_match.empty else None
    return ledger_record, statement_record


def _to_serializable(record: dict) -> dict:
    """
    pandas loads 'date' as a Timestamp object, which json.dumps cannot
    handle on its own. Convert it (and anything similarly non-plain)
    to a plain string before it ever reaches the LLM call.
    """
    clean = {}
    for key, value in record.items():
        if hasattr(value, "isoformat"):  # Timestamp, datetime, date all have this
            clean[key] = value.strftime("%Y-%m-%d")
        else:
            clean[key] = value
    return clean


def main():
    ledger, statement = load_data()
    results = run_reconciliation()
    needs_llm = results["needs_llm"]

    if needs_llm.empty:
        print("\nNo ambiguous exceptions this run — rules resolved everything confidently.")
        return

    print(f"\n=== Investigating {len(needs_llm)} ambiguous exception(s) ===\n")
    for _, row in needs_llm.iterrows():
        txn_id = row["txn_id"]
        ledger_record, statement_record = get_original_records(txn_id, ledger, statement)

        investigation = investigate_exception(ledger_record, statement_record)

        print(f"--- {txn_id} ---")
        print(f"  exception_type:      {investigation['exception_type']}")
        print(f"  probable_cause:      {investigation['probable_cause']}")
        print(f"  confidence:          {investigation['confidence']}")
        print(f"  evidence:            {investigation['evidence']}")
        print(f"  recommended_action:  {investigation['recommended_action']}")
        print(f"  severity:            {investigation['severity']}")
        print()


if __name__ == "__main__":
    main()