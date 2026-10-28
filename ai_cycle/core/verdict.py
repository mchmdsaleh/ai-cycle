from __future__ import annotations

import json

VERDICTS = ("PASS", "CHANGES_REQUIRED", "NEEDS_HUMAN")


def review_json(text: str) -> dict | None:
    try:
        if "```json" in text:
            data = json.loads(text.split("```json", 1)[1].split("```", 1)[0].strip())
        else:
            data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def parse_verdict(text: str) -> str:
    """Require an explicit verdict; prose containing PASS is not acceptance evidence."""
    data = review_json(text)
    if data is not None:
        verdict = str(data.get("verdict", "")).strip().upper()
        if data.get("blockers"):
            return "CHANGES_REQUIRED"
        if data.get("spec_questions"):
            return "NEEDS_HUMAN"
        return verdict if verdict in VERDICTS else "UNKNOWN"
    for line in reversed(text.splitlines()):
        verdict = line.strip().upper().removeprefix("VERDICT: ")
        if verdict in VERDICTS:
            return verdict
    return "UNKNOWN"
