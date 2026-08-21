from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console
from rich.live import Live

from ai_cycle.agents.claude import claude_review
from ai_cycle.agents.codex import codex_implement
from ai_cycle.agents.copilot import copilot_review
from ai_cycle.agents.postmortem import propose_rule
from ai_cycle.core.config import get_project_paths, load_config, read, write
from ai_cycle.core.git import assert_clean_worktree, assert_git_repo, current_branch, get_diff
from ai_cycle.core.runner import die, require_commands
from ai_cycle.core.verdict import parse_verdict
from ai_cycle.resume import load_previous_feedback, sha256_text
from ai_cycle.ui.panels import render_header, render_verdict_table
from ai_cycle.ui.progress import CycleProgress


def build_feedback(copilot: str, claude: str, validation_log: str | None = None) -> str:
    parts = []
    if parse_verdict(copilot) != "PASS":
        parts.append("COPILOT REVIEW:\n" + copilot)
    if parse_verdict(claude) != "PASS":
        parts.append("CLAUDE CODE REVIEW:\n" + claude)
    if validation_log:
        parts.append("VALIDATION OUTPUT:\n" + validation_log)
    return "\n\n".join(parts)


def run_validation(commands: list[str], run_dir: Path, cwd: Path) -> bool:
    from ai_cycle.core.runner import run as run_cmd

    logs = []
    ok = True
    for raw in commands:
        cmd = ["bash", "-lc", raw]
        p = run_cmd(cmd, cwd=cwd, timeout=1800)
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

    require_commands(["git", "codex", "copilot", "claude", "bash"])
    assert_git_repo(root)
    assert_clean_worktree(root, allow_dirty)

    branch = current_branch(root)

    cfg = load_config(state)
    max_attempts = max_attempts or int(cfg.get("max_attempts", 2))
    validation_commands = cfg.get("validation_commands", [])

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
        progress.add_stage("🔍 Copilot Review")
        progress.add_stage("🔍 Claude Review")

        with Live(progress.render(), console=console, refresh_per_second=1) as live:
            progress.start_stage("🔧 Codex Implementer")
            live.update(progress.render())
            codex_implement(spec, rules, feedback, run_dir, root)
            progress.complete_stage("🔧 Codex Implementer")
            live.update(progress.render())

            diff = get_diff(root)
            write(run_dir / "diff.patch", diff)

            progress.start_stage("🔍 Copilot Review")
            progress.start_stage("🔍 Claude Review")
            live.update(progress.render())

            with ThreadPoolExecutor(max_workers=2) as executor:
                f_copilot = executor.submit(copilot_review, spec, rules, diff, run_dir, root)
                f_claude = executor.submit(claude_review, spec, rules, diff, run_dir)
                copilot = f_copilot.result()
                claude = f_claude.result()

            progress.complete_stage("🔍 Copilot Review")
            progress.complete_stage("🔍 Claude Review")
            live.update(progress.render())

        cv = parse_verdict(copilot)
        clv = parse_verdict(claude)
        render_verdict_table(console, cv, clv)

        if cv == "NEEDS_HUMAN" or clv == "NEEDS_HUMAN":
            feedback = build_feedback(copilot, claude)
            write(run_dir / "spec-questions.txt", feedback)
            console.print("\n[bold yellow]========== STOPPED FOR HUMAN DECISION (NEEDS_HUMAN) ==========[/bold yellow]")
            console.print("One or more reviewers identified a spec ambiguity or product architecture conflict.")
            console.print(f"Review details saved in: {run_dir / 'spec-questions.txt'}")
            console.print("Please review and resolve the question in .ai-cycle/spec.md before re-running.")
            return

        if cv != "PASS" or clv != "PASS":
            feedback = build_feedback(copilot, claude)
            write(run_dir / "feedback.txt", feedback)
            if attempt < max_attempts:
                continue
            write(base_run / "terminal-feedback.txt", feedback)
            propose_rule(spec, feedback, run_dir, root)
            die(f"Review failed after {max_attempts} attempt(s). See {run_dir}")

        console.rule("DETERMINISTIC VALIDATION")
        validation_ok = run_validation(validation_commands, run_dir, root)
        validation_log = read(run_dir / "validation.txt")

        if not validation_ok:
            feedback = build_feedback(copilot, claude, validation_log)
            write(run_dir / "feedback.txt", feedback)
            if attempt < max_attempts:
                continue
            write(base_run / "terminal-feedback.txt", feedback)
            propose_rule(spec, feedback, run_dir, root)
            die(f"Validation failed after {max_attempts} attempt(s). See {run_dir}")

        console.rule("HUMAN ACCEPTANCE GATE")
        console.print("Automated cycle passed.")
        console.print("Review the actual behavior and git diff yourself:")
        console.print("  git diff")
        console.print(f"  cat {run_dir / 'review-copilot.txt'}")
        console.print(f"  cat {run_dir / 'review-claude.txt'}")
        console.print(f"  cat {run_dir / 'validation.txt'}")
        console.print("\nNo commit or push was performed.")
        return
