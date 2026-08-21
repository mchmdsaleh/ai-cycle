from __future__ import annotations

import tempfile
from pathlib import Path

from ai_cycle.core.config import write
from ai_cycle.core.runner import die, run


def review_prompt(name: str, spec: str, rules: str, diff: str) -> str:
    return f"""
You are {name}, an INDEPENDENT adversarial code reviewer.

You did NOT see the implementer's reasoning and must not assume the change is correct.

SPEC:
{spec}

PERMANENT RULES:
{rules}

GIT DIFF:
{diff}

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
{{
  "verdict": "PASS | CHANGES_REQUIRED | NEEDS_HUMAN",
  "summary": "Brief summary",
  "blockers": [],
  "spec_questions": [],
  "non_blocking": []
}}
```

And end with one of:
VERDICT: PASS
VERDICT: NEEDS_HUMAN
VERDICT: CHANGES_REQUIRED
""".strip()


def copilot_review(spec: str, rules: str, diff: str, run_dir: Path, cwd: Path) -> str:
    prompt = review_prompt("REVIEWER A (GitHub Copilot CLI)", spec, rules, diff)

    with tempfile.NamedTemporaryFile("w+", suffix="-prompt.txt", encoding="utf-8") as tf:
        tf.write(prompt)
        tf.flush()
        cmd = [
            "copilot",
            "-s", "-p", f"@{tf.name}",
            "--available-tools=view,grep,glob",
            "--deny-tool=write",
        ]
        p = run(cmd, cwd=cwd)
        write(run_dir / "review-copilot.txt", p.stdout)
        if p.returncode != 0:
            die("Copilot reviewer failed.")
        return p.stdout
