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


def codex_plan_spec(request: str | None, input_path: Path | None, cwd: Path, *, planning_context: str | None = None) -> str:
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
    if planning_context is not None:
        prompt += f"""

## OpenSpec Output Contract (overrides single spec output and file delivery)
{planning_context}
Return ONLY a JSON object, without code fences, with a `files` object mapping
artifact relative paths to their complete text contents. Include proposal.md,
design.md, wireframe.md, tasks.md, readiness.json and specs/<capability>/spec.md.
Follow schema templates rather than the single-document output structure above.
Use English headings and Indonesian explanations. Reconcile supplied answers
across ALL artifacts, retaining explicit requirements and existing capability
specs. Remove resolved questions. Preserve unresolved questions in proposal and
readiness.json. readiness.json is a JSON string with status draft/ready and a
blockers array; ready requires no unresolved material business decisions.
Readiness applies to the explicitly selected implementation scope. If the user
has deferred decisions AND all dependent requirements, retain them under
deferredDecisions (not blockers). blockers contains only unresolved decisions
required for the current scope. Set ready when that scope has no blockers;
do not mark deferred decisions resolved or expand the agreed scope. Keep
proposal/design status consistent with this scoped readiness. Do not move an
active blocker to deferred without the user's explicit scope decision.
Read related openspec/specs in the repository before writing delta requirements.
For ADDED requirements, keep the description between the Requirement heading
and its first Scenario at most 500 characters. Put examples, edge cases and
details in scenarios, or split distinct behaviors into separate requirements.
For MODIFIED requirements, preserve the complete existing requirement and all
scenarios; do not remove behavior just to meet a length limit.
If referenced review feedback concerns a different feature than this change,
report the scope mismatch in proposal/readiness rather than adding unrelated
requirements. A user answer alone does not authorize expanding feature scope.
Do not implement source, mark acceptance as passed, or claim tests were run.
"""

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


def codex_implement(spec: str, rules: str, feedback: str | None, run_dir: Path, cwd: Path, *, task_path: Path | None = None, implementer: str = "codex") -> str:
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
    if task_path is not None:
        prompt += f"\nTrack implementation in {task_path}. Only mark tasks done after their verification succeeds. Preserve task descriptions. You may append verification notes under a final '## Implementation evidence' section, but must not modify other OpenSpec planning artifacts or archive the change."

    if implementer == "codex":
        cmd = ["codex", "exec", "--ephemeral", "--sandbox", "workspace-write", "-"]
        env = codex_env()
    elif implementer == "agy":
        cmd = ["agy", "--print", "--mode", "accept-edits", "--sandbox", "--output-format", "text"]
        env = os.environ.copy()
    else:
        die("Unknown implementer. Choose codex or agy.")
    p = run(cmd, cwd=cwd, input_text=prompt, env=env, output_path=run_dir / "implementer.txt")
    if p.returncode != 0:
        die(f"{implementer} implementer failed. See {run_dir / 'implementer.txt'}")
    return p.stdout
