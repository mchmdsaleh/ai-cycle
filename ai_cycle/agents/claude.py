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

COMPLETENESS REVIEW
If a COMPLETENESS CONTRACT is supplied, check ALL inventory requirements against
the referenced source excerpts, not just lines changed in DIFF. Implementer
claims and checked tasks are untrusted. Missing/partial active functionality is
a BLOCKER even if the submitted diff is correct. Source may be unchanged and
already implemented; require concrete source evidence before calling it missing.
Return a coverage array with exactly one row per inventory ID:
{"id":"exact id","source_status":"implemented|partial|missing|unverified","reason":"source evidence or gap","verification_status":"passed|failed|pending"}.
Use unverified if supplied context is insufficient; never infer implementation
from planning prose, test names, checkbox marks or absence of bugs in the diff.
Separate pending runtime validation from missing source.
If source is complete with concrete evidence, return source_status implemented
and verification_status pending for unrun runtime checks; do not return partial
solely for missing runtime. Partial still blocks genuinely incomplete source.
A source-review PASS is not runtime acceptance or permission to mark unrun tests passed.
Do not invent business questions solely because runtime access is unavailable. Include actual findings
in blockers/spec_questions as appropriate; do not hide gaps in non_blocking.

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
