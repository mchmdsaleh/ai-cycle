from __future__ import annotations

import json

VERDICTS = ("PASS", "CHANGES_REQUIRED", "NEEDS_HUMAN")


def parse_verdict(text: str) -> str:
    """Extract a verdict from reviewer output: JSON block first, then fuzzy fallback."""
    try:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            data = json.loads(json_str)
            v = str(data.get("verdict", "")).strip().upper()
            if v in VERDICTS:
                return v
            if "REJECT" in v or "FAIL" in v or "CHANGES" in v:
                return "CHANGES_REQUIRED"
        elif "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            data = json.loads(text[start:end + 1])
            v = str(data.get("verdict", "")).strip().upper()
            if v in VERDICTS:
                return v
            if "REJECT" in v or "FAIL" in v or "CHANGES" in v:
                return "CHANGES_REQUIRED"
    except Exception:
        pass

    for line in reversed(text.splitlines()):
        u_line = line.strip().upper()
        if "VERDICT: PASS" in u_line or u_line == "PASS":
            return "PASS"
        if "VERDICT: NEEDS_HUMAN" in u_line or u_line == "NEEDS_HUMAN" or "NEEDS_HUMAN" in u_line:
            return "NEEDS_HUMAN"
        if (
            "VERDICT: CHANGES_REQUIRED" in u_line
            or u_line == "CHANGES_REQUIRED"
            or "CHANGES_REQUIRED" in u_line
            or "REJECT" in u_line
        ):
            return "CHANGES_REQUIRED"

    upper_text = text.upper()
    if "CHANGES_REQUIRED" in upper_text or "REJECT" in upper_text or "FAIL" in upper_text or "BLOCKER" in upper_text:
        return "CHANGES_REQUIRED"
    if "NEEDS_HUMAN" in upper_text or "SPEC_QUESTION" in upper_text:
        return "NEEDS_HUMAN"
    if "PASS" in upper_text:
        return "PASS"

    return "UNKNOWN"
