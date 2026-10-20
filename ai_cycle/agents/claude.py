from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from ai_cycle.core.runner import die, run

REVIEW_INSTRUCTIONS = """
You are REVIEWER B (Claude Code CLI), an INDEPENDENT adversarial code reviewer.

Review the SPEC, RULES, and DIFF supplied below.
You did NOT see the implementer's reasoning and must not assume the change is correct.

CLASSIFICATION RULES
--------------------
Categorize all findings into one of three severity classes:

1. BLOCKER (Must cause CHANGES_REQUIRED):
   - Concrete violation of an explicit requirement in SPEC.md
   - Concrete violation of acceptance criteria
   - Concrete violation of RULES.md
   - Demonstrable correctness bug or security regression not explicitly required by spec

2. SPEC_QUESTION (Must cause NEEDS_HUMAN):
   - The specification conflicts with existing system behavior/architecture
   - The specification itself contains business logic ambiguity or missing product decisions
   - Do NOT guess or override product decisions. Stop for human input.

3. NON_BLOCKING (Does not block PASS):
   - Style preferences, minor cleanup
   - Redundant but correct code
   - Intentional behavior explicitly requested by spec that differs from legacy code

VERDICT DEFINITIONS
-------------------
- CHANGES_REQUIRED: At least 1 BLOCKER exists.
- NEEDS_HUMAN: No BLOCKER, but at least 1 SPEC_QUESTION must be resolved by a human.
- PASS: No BLOCKER and no unresolved SPEC_QUESTION.

Output format:
Your final output MUST include a structured JSON block:
```json
{
  "verdict": "PASS | CHANGES_REQUIRED | NEEDS_HUMAN",
  "summary": "Brief summary",
  "blockers": [],
  "spec_questions": [],
  "non_blocking": []
}
```

And end with one of:
VERDICT: PASS
VERDICT: NEEDS_HUMAN
VERDICT: CHANGES_REQUIRED
""".strip()


def claude_review(spec: str, rules: str, diff: str, run_dir: Path, model: str | None = None) -> str:
    # Isolate Claude Code from the real repo and keep review to one model call.
    with tempfile.TemporaryDirectory(prefix="ai-cycle-review-") as td:
        box = Path(td)
        prompt = f"{REVIEW_INSTRUCTIONS}\n\nSPEC:\n{spec}\n\nRULES:\n{rules}\n\nDIFF:\n{diff}"

        cmd = [
            "claude",
            "--model",
            os.getenv("AI_CYCLE_REVIEW_MODEL") or model or "kr/claude-opus-5",
            "-p",
            "--safe-mode",
            "--tools",
            "",
            "--no-session-persistence",
            "--effort",
            "low",
            "--output-format",
            "text",
        ]
        try:
            p = run(
                cmd,
                cwd=box,
                input_text=prompt,
                timeout=300,
                quiet=True,
                output_path=run_dir / "review-claude.txt",
            )
        except subprocess.TimeoutExpired:
            die("Claude reviewer timed out after 300s. Check 9Router or choose another review_model.")
        if p.returncode != 0:
            die(f"Claude Code reviewer failed:\n{p.stdout.strip()}")
        return p.stdout
