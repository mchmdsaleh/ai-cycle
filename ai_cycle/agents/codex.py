from __future__ import annotations

import os
from pathlib import Path

from ai_cycle.core.config import write
from ai_cycle.core.runner import die, run


def codex_env() -> dict:
    env = os.environ.copy()
    # 9Router is used as the gateway for Codex when these are set.
    base = os.getenv("NINEROUTER_BASE_URL", "http://127.0.0.1:20128")
    api_key = os.getenv("NINEROUTER_API_KEY")
    if api_key:
        env["OPENAI_BASE_URL"] = base
        env["OPENAI_API_KEY"] = api_key
    return env


def codex_implement(spec: str, rules: str, feedback: str | None, run_dir: Path, cwd: Path) -> str:
    prompt = f"""
You are the IMPLEMENTER in a controlled software-engineering cycle.

SOURCE OF TRUTH
---------------
SPEC:
{spec}

PERMANENT RULES:
{rules}

{"REVIEW FEEDBACK TO FIX:" + chr(10) + feedback if feedback else ""}

TASK
----
Implement the spec in the current repository.

Constraints:
- Modify only files necessary for the spec.
- Do not change the spec or acceptance criteria.
- Do not git push.
- Do not rewrite or weaken tests merely to make them pass.
- Preserve unrelated user changes.
- Run focused checks when useful, but final validation is handled separately.
- Stop when the implementation is complete.

At the end, give a concise summary of files changed and assumptions.
""".strip()

    cmd = ["codex", "exec", "--ephemeral", "--sandbox", "workspace-write", "-"]
    p = run(cmd, cwd=cwd, input_text=prompt, env=codex_env())
    write(run_dir / "implementer.txt", p.stdout)
    if p.returncode != 0:
        die("Codex implementer failed.")
    return p.stdout
