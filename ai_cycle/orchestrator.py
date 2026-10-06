from __future__ import annotations

import subprocess
import json
from pathlib import Path

from rich.console import Console
from rich.live import Live

from ai_cycle.agents.claude import claude_review
from ai_cycle.agents.codex import codex_implement
from ai_cycle.agents.postmortem import propose_rule
from ai_cycle.core.config import get_project_paths, load_config, read, write
from ai_cycle.core.git import assert_clean_worktree, assert_git_repo, current_branch, get_diff
from ai_cycle.core.runner import die, require_commands
from ai_cycle.core.verdict import parse_verdict
from ai_cycle.resume import load_previous_feedback, sha256_text
from ai_cycle.ui.panels import render_header, render_verdict_table
from ai_cycle.ui.progress import CycleProgress

MAX_REVIEW_DIFF_BYTES = 1_000_000


def build_feedback(claude: str, validation_log: str | None = None) -> str:
    parts = []
    if claude and parse_verdict(claude) != "PASS":
        parts.append("CLAUDE CODE REVIEW:\n" + compact_review(claude))
    if validation_log:
        parts.append("VALIDATION OUTPUT:\n" + validation_log)
    return "\n\n".join(parts)


def compact_review(text: str) -> str:
    """Return the structured reviewer JSON when present; it is enough for retries."""
    try:
        if "```json" in text:
            return json.dumps(json.loads(text.split("```json")[1].split("```")[0].strip()), indent=2)
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            return json.dumps(json.loads(text[start : end + 1]), indent=2)
    except Exception:
        pass
    return text.strip()


def run_validation(commands: list[str], run_dir: Path, cwd: Path, progress=None) -> bool:
    from ai_cycle.core.runner import run as run_cmd

    logs = []
    ok = True
    for index, raw in enumerate(commands, 1):
        cmd = ["bash", "-lc", raw]
        log_path = run_dir / f"validation-command-{index}.txt"
        if progress:
            progress.log_path = log_path
        p = run_cmd(cmd, cwd=cwd, timeout=1800, output_path=log_path)
        logs.append(f"$ {raw}\n{p.stdout}\n[exit={p.returncode}]\n")
        if p.returncode != 0:
            ok = False
    write(run_dir / "validation.txt", "\n".join(logs))
    return ok


def execute_cycle(
    resume: bool = False,
    allow_dirty: bool = False,
    max_attempts: int | None = None,
    root: Path | None = None,
):
    console = Console()
    root = root or Path.cwd()
    paths = get_project_paths(root)
    state, runs = paths["state"], paths["runs"]

    require_commands(["git", "codex", "claude", "bash"])
    assert_git_repo(root)
    assert_clean_worktree(root, allow_dirty)

    branch = current_branch(root)

    cfg = load_config(state)
    max_attempts = max_attempts or int(cfg.get("max_attempts", 2))
    validation_commands = cfg.get("validation_commands", [])
    base_branch = cfg.get("base_branch")
    review_model = cfg.get("review_model")

    spec_path = state / "spec.md"
    rules_path = state / "RULES.md"
    if not spec_path.exists() or not rules_path.exists():
        die("Missing .ai-cycle/spec.md or .ai-cycle/RULES.md")

    spec = read(spec_path)
    rules = read(rules_path)

    runs.mkdir(parents=True, exist_ok=True)
    run_id = subprocess.check_output(["date", "+%Y%m%d-%H%M%S"], text=True).strip()
    base_run = runs / run_id
    base_run.mkdir()

    metadata = {"branch": branch, "spec_hash": sha256_text(spec)}
    write(base_run / "metadata.json", __import__("json").dumps(metadata, indent=2))

    feedback = None
    resume_info = None

    if resume:
        previous = load_previous_feedback(runs, current_run=base_run, spec=spec, branch=branch)
        if previous:
            feedback = previous["feedback"]
            resume_info = previous["run"].name
            write(base_run / "resumed-from.txt", str(previous["run"]))
        else:
            console.print("[yellow][INFO][/yellow] No compatible failed run found to resume.")

    render_header(console, branch, metadata["spec_hash"], resume_info)

    for attempt in range(1, max_attempts + 1):
        console.rule(f"ATTEMPT {attempt}/{max_attempts}")
        run_dir = base_run / f"attempt-{attempt}"
        run_dir.mkdir()

        progress = CycleProgress(console)
        progress.add_stage("🔧 Codex Implementer")
        progress.add_stage("✅ Validation")
        progress.add_stage("🔍 Claude Review")

        with Live(get_renderable=progress.render, console=console, refresh_per_second=4) as live:
            progress.start_stage("🔧 Codex Implementer", run_dir / "implementer.txt")
            live.update(progress.render())
            codex_implement(spec, rules, feedback, run_dir, root)
            progress.complete_stage("🔧 Codex Implementer")
            live.update(progress.render())

            diff = get_diff(root, base_branch)
            write(run_dir / "diff.patch", diff)
            diff_bytes = len(diff.encode("utf-8"))
            if diff_bytes > MAX_REVIEW_DIFF_BYTES:
                die(
                    f"Review diff is too large ({diff_bytes / 1_000_000:.1f} MB). "
                    "Commit unrelated changes or fix base_branch in .ai-cycle/config.json. "
                    f"See {run_dir / 'diff.patch'}"
                )

            progress.start_stage("✅ Validation")
            live.update(progress.render())
            validation_ok = run_validation(validation_commands, run_dir, root, progress)
            progress.complete_stage("✅ Validation", success=validation_ok)
            live.update(progress.render())

            if not validation_ok:
                validation_log = read(run_dir / "validation.txt")
                feedback = build_feedback("", validation_log)
                write(run_dir / "feedback.txt", feedback)
                if attempt < max_attempts:
                    continue
                write(base_run / "terminal-feedback.txt", feedback)
                if cfg.get("postmortem", False):
                    with console.status("Postmortem: generating rule proposal..."):
                        propose_rule(spec, feedback, run_dir, root)
                die(f"Validation failed after {max_attempts} attempt(s). See {run_dir}")

            progress.start_stage("🔍 Claude Review", run_dir / "review-claude.txt")
            live.update(progress.render())

            claude = claude_review(spec, rules, diff, run_dir, model=review_model)

            progress.complete_stage("🔍 Claude Review", success=parse_verdict(claude) == "PASS")
            live.update(progress.render())

        clv = parse_verdict(claude)
        render_verdict_table(console, clv)

        if clv == "NEEDS_HUMAN":
            feedback = build_feedback(claude)
            write(run_dir / "spec-questions.txt", feedback)
            console.print("\n[bold yellow]========== STOPPED FOR HUMAN DECISION (NEEDS_HUMAN) ==========[/bold yellow]")
            console.print("One or more reviewers identified a spec ambiguity or product architecture conflict.")
            console.print(f"Review details saved in: {run_dir / 'spec-questions.txt'}")
            console.print("Please review and resolve the question in .ai-cycle/spec.md before re-running.")
            return

        if clv != "PASS":
            feedback = build_feedback(claude)
            write(run_dir / "feedback.txt", feedback)
            if attempt < max_attempts:
                continue
            write(base_run / "terminal-feedback.txt", feedback)
            if cfg.get("postmortem", False):
                with console.status("Postmortem: generating rule proposal..."):
                    propose_rule(spec, feedback, run_dir, root)
            die(f"Review failed after {max_attempts} attempt(s). See {run_dir}")

        console.rule("HUMAN ACCEPTANCE GATE")
        console.print("Automated cycle passed.")
        console.print("Review the actual behavior and git diff yourself:")
        console.print("  git diff")
        console.print(f"  cat {run_dir / 'review-claude.txt'}")
        console.print(f"  cat {run_dir / 'validation.txt'}")
        console.print("\nNo commit or push was performed.")
        return
