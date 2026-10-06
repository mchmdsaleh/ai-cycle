from __future__ import annotations

import os
import tempfile
from importlib.resources import files
from pathlib import Path

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


def codex_plan_spec(request: str | None, input_path: Path | None, cwd: Path) -> str:
    source = f"User request:\n{request}" if request else ""
    if input_path:
        source += f"\n\nInput artifact: {input_path.resolve()}"
    instructions = files("ai_cycle").joinpath("SPEC_INSTRUCTIONS.md").read_text(encoding="utf-8")
    prompt = f"""{instructions}

## AI Cycle Execution

You are in PLAN MODE. Do not modify project files. Return only the completed
spec Markdown; ai-cycle writes it to `.ai-cycle/spec.md` after you succeed.

## Current Input
{source.strip()}
""".strip()

    with tempfile.TemporaryDirectory(prefix="ai-cycle-spec-") as td:
        output = Path(td) / "spec.md"
        cmd = [
            "codex", "exec", "--ephemeral", "--sandbox", "read-only",
            "--output-last-message", str(output), "-",
        ]
        p = run(cmd, cwd=cwd, input_text=prompt, env=codex_env(), quiet=True)
        if p.returncode != 0 or not output.exists():
            die("Codex spec planner failed.")
        spec = output.read_text(encoding="utf-8").strip()
        if not spec:
            die("Codex spec planner returned an empty spec.")
        return spec + "\n"


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
    p = run(cmd, cwd=cwd, input_text=prompt, env=codex_env(), output_path=run_dir / "implementer.txt")
    if p.returncode != 0:
        die("Codex implementer failed.")
    return p.stdout
