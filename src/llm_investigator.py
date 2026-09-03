"""
LLM investigator: called ONLY on exceptions the deterministic rules
couldn't confidently classify (labels ending in '_needs_review').

This is the "AI handles what requires judgment" boundary — everything
classifiable by a named rule never reaches the LLM at all.

Uses Groq (free tier, no billing required) instead of a paid API.
Forces structured JSON output and validates it before use. A response
that doesn't match the schema is treated as a failure, not silently
accepted — this matters for a financial system.
"""

import json
import os

try:
    from groq import Groq
except ImportError:
    Groq = None

REQUIRED_FIELDS = {
    "exception_type": str,
    "probable_cause": str,
    "confidence": (int, float),
    "evidence": list,
    "recommended_action": str,
    "severity": str,
}
ALLOWED_SEVERITY = {"low", "medium", "high"}

SYSTEM_PROMPT = """You are a financial reconciliation exception investigator.
You will be given one ledger record and one statement record (or a record
missing its counterpart entirely). Classify the discrepancy.

Respond with ONLY a JSON object, no other text, matching exactly this shape:
{
  "exception_type": "<short snake_case category>",
  "probable_cause": "<one sentence>",
  "confidence": <float 0.0-1.0>,
  "evidence": ["<short factual observation>", "..."],
  "recommended_action": "<one sentence>",
  "severity": "low" | "medium" | "high"
}

You are strictly an investigator. You never suggest creating, deleting,
or modifying a financial transaction. You only classify and recommend
review actions."""


def validate_response(data: dict) -> tuple[bool, str]:
    """Returns (is_valid, error_message). Never trust an LLM response blind."""
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            return False, f"missing field: {field}"
        if not isinstance(data[field], expected_type):
            return False, f"field '{field}' has wrong type"
    if not (0.0 <= float(data["confidence"]) <= 1.0):
        return False, "confidence out of range"
    if data["severity"] not in ALLOWED_SEVERITY:
        return False, "invalid severity value"
    return True, ""


def investigate_exception(ledger_record: dict, statement_record: dict | None, api_key: str | None = None) -> dict:
    """
    Calls Groq for a single ambiguous exception. Returns a validated
    dict, or a fallback 'needs_manual_review' dict if the call fails or
    the response doesn't pass validation — never crashes the pipeline
    on a bad LLM response.
    """
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if Groq is None or not api_key:
        return _fallback("LLM unavailable (no client/key) — manual review required")

    client = Groq(api_key=api_key)
    user_content = (
        f"Ledger record: {json.dumps(ledger_record)}\n"
        f"Statement record: {json.dumps(statement_record) if statement_record else 'NONE — no counterpart found'}"
    )

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            max_tokens=400,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text)
    except (json.JSONDecodeError, Exception) as e:
        return _fallback(f"LLM call/parse failed: {e}")

    is_valid, error = validate_response(data)
    if not is_valid:
        return _fallback(f"LLM response failed schema validation: {error}")

    return data


def _fallback(reason: str) -> dict:
    return {
        "exception_type": "needs_manual_review",
        "probable_cause": reason,
        "confidence": 0.0,
        "evidence": [],
        "recommended_action": "Escalate to finance team for manual investigation.",
        "severity": "medium",
    }


if __name__ == "__main__":
    mock_good_response = {
        "exception_type": "settlement_delay",
        "probable_cause": "T+2 settlement cycle, common for this gateway",
        "confidence": 0.91,
        "evidence": ["Transaction date: 2026-08-20", "Settlement date: 2026-08-22", "Amount matches exactly"],
        "recommended_action": "No action needed; monitor settlement completion.",
        "severity": "low",
    }
    mock_bad_response = {"exception_type": "settlement_delay", "confidence": 1.5}

    ok, err = validate_response(mock_good_response)
    print(f"Valid response test:   passed={ok}")
    assert ok, "Expected valid response to pass"

    ok, err = validate_response(mock_bad_response)
    print(f"Invalid response test: passed={not ok} (correctly rejected: {err})")
    assert not ok, "Expected invalid response to fail"

    print("\nAll validation tests passed.")