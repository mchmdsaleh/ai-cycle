from __future__ import annotations

import tempfile
from pathlib import Path

from ai_cycle.core.config import write
from ai_cycle.core.runner import run


def propose_rule(spec: str, feedback: str, run_dir: Path, cwd: Path):
    """Rule proposal only. Human decides whether to append it to RULES.md."""
    prompt = f"""
You are a postmortem agent. Based only on this failed engineering cycle,
decide whether the failure reveals a reusable systemic rule.

SPEC:
{spec}

FAILURE / REVIEW EVIDENCE:
{feedback}

Return either:
NO_RULE

or:

RULE_PROPOSAL:
<one concise reusable rule>

REASON:
<why this is systemic rather than a one-off typo>
""".strip()

    with tempfile.TemporaryDirectory(prefix="ai-cycle-postmortem-") as td:
        box = Path(td)
        cmd = ["claude", "--model", "kr/claude-opus-5", "-p", prompt, "--dangerously-skip-permissions"]
        p = run(cmd, cwd=box)
        write(run_dir / "rule-proposal.txt", p.stdout)
