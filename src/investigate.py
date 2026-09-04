"""
Runs the full reconciliation pipeline, then sends only the genuinely
ambiguous exceptions (needs_llm) to the LLM investigator, one at a time.

This is the file that demonstrates the complete story:
  deterministic rules -> named exceptions -> AI only where rules can't decide
  -> AI's own confidence closes the loop: auto-resolve or escalate to a human

The routing decision (auto-resolve vs. escalate) is made by the system
itself based on the AI's confidence score — this is the "agent" behavior:
it doesn't just recommend, it decides what happens next, within a bounded
set of outcomes. It still never modifies a transaction either way.
"""

import json
import pandas as pd
from datetime import datetime, timezone
from reconcile import run_reconciliation, load_data
from llm_investigator import investigate_exception

AUTO_RESOLVE_CONFIDENCE_THRESHOLD = 0.85


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


def route_by_confidence(investigation: dict) -> str:
    """
    This is the loop-closing step: the system decides what happens next
    based on the AI's own confidence, instead of a human reading every
    single recommendation. Still never touches the transaction itself —
    only decides which queue it belongs in.
    """
    if investigation["confidence"] >= AUTO_RESOLVE_CONFIDENCE_THRESHOLD:
        return "auto_resolved"
    return "escalated_to_human"


def main():
    ledger, statement = load_data()
    results = run_reconciliation()
    needs_llm = results["needs_llm"]

    rule_resolved_count = len(results["classified"]) - len(needs_llm)
    investigations = []

    if not needs_llm.empty:
        print(f"\n=== Investigating {len(needs_llm)} ambiguous exception(s) ===\n")
        for _, row in needs_llm.iterrows():
            txn_id = row["txn_id"]
            ledger_record, statement_record = get_original_records(txn_id, ledger, statement)
            investigation = investigate_exception(ledger_record, statement_record)
            routing = route_by_confidence(investigation)

            print(f"--- {txn_id} ---")
            print(f"  exception_type:      {investigation['exception_type']}")
            print(f"  probable_cause:      {investigation['probable_cause']}")
            print(f"  confidence:          {investigation['confidence']}")
            print(f"  evidence:            {investigation['evidence']}")
            print(f"  recommended_action:  {investigation['recommended_action']}")
            print(f"  severity:            {investigation['severity']}")
            print(f"  ROUTED TO:           {routing.upper()}")
            print()

            investigations.append({"txn_id": txn_id, **investigation, "routed_to": routing})
    else:
        print("\nNo ambiguous exceptions this run — rules resolved everything confidently.")

    auto_resolved = [i for i in investigations if i["routed_to"] == "auto_resolved"]
    escalated = [i for i in investigations if i["routed_to"] == "escalated_to_human"]

    # NOTE: rule_resolved_count is scoped to len(classified) — the exception
    # list spans BOTH ledger-only and statement-only exceptions, which is a
    # different (larger) population than "total ledger transactions". Kept
    # as two explicitly separate numbers rather than one blended total, to
    # avoid the same silent double-counting bug caught earlier in the
    # dashboard's match-rate calculation.
    total_items_classified = len(results["classified"])

    print("=== Loop Closure Summary ===")
    print(f"Items classified (ledger transactions + statement-only exceptions): {total_items_classified}")
    print(f"Resolved by deterministic rules:  {rule_resolved_count}")
    print(f"Auto-resolved by AI (confidence >= {AUTO_RESOLVE_CONFIDENCE_THRESHOLD}): {len(auto_resolved)}")
    print(f"Escalated to human review:        {len(escalated)}")
    print(f"Total requiring zero human action: {rule_resolved_count + len(auto_resolved)} / {total_items_classified}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_ledger_transactions": results["throughput"]["total"],
        "total_items_classified": total_items_classified,
        "throughput_txn_per_sec": round(results["throughput"]["txn_per_sec"], 1),
        "accuracy_vs_ground_truth": results["scoring"],
        "rule_resolved_count": rule_resolved_count,
        "ai_auto_resolved_count": len(auto_resolved),
        "escalated_to_human_count": len(escalated),
        "auto_resolve_confidence_threshold": AUTO_RESOLVE_CONFIDENCE_THRESHOLD,
        "investigations": investigations,
    }
    with open("data/reconciliation_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull audit report written to data/reconciliation_report.json")


if __name__ == "__main__":
    main()