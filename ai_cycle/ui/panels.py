from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_cycle import __version__
from ai_cycle.core.config import get_project_paths

VERDICT_STYLE = {
    "PASS": "bold green",
    "CHANGES_REQUIRED": "bold red",
    "NEEDS_HUMAN": "bold yellow",
    "UNKNOWN": "dim",
}


def render_header(console: Console, branch: str, spec_hash: str, resume_info: str | None = None):
    lines = [
        f"[bold]🤖 AI Cycle v{__version__}[/bold]",
        f"Branch: {branch}",
        f"Spec:   {spec_hash[:12]}...(spec.md)",
    ]
    if resume_info:
        lines.append(f"Mode:   RESUME from run {resume_info}")
    else:
        lines.append("Mode:   FRESH")
    console.print(Panel("\n".join(lines), expand=False))


def render_verdict_table(console: Console, claude_verdict: str, blockers: int = 0, spec_questions: int = 0):
    table = Table(title="📊 Review Verdict", show_header=False)
    table.add_column("Reviewer")
    table.add_column("Verdict")

    def styled(v: str) -> str:
        icon = "✅" if v == "PASS" else ("⚠️" if v == "NEEDS_HUMAN" else "❌")
        return f"[{VERDICT_STYLE.get(v, 'dim')}]{icon} {v}[/{VERDICT_STYLE.get(v, 'dim')}]"

    table.add_row("Claude", styled(claude_verdict))
    console.print(table)
    console.print(f"[dim]Blockers: {blockers}  |  Spec Questions: {spec_questions}[/dim]")


def _run_summary(run_dir: Path) -> dict:
    metadata_path = run_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    attempts = sorted(run_dir.glob("attempt-*"))
    max_attempts = len(attempts)

    terminal_feedback = (run_dir / "terminal-feedback.txt").exists()
    spec_questions = any((a / "spec-questions.txt").exists() for a in attempts)

    if spec_questions:
        result = "🟡 NEEDS_HUMAN"
    elif terminal_feedback:
        result = "❌ FAIL"
    elif attempts and not (run_dir / "feedback.txt").exists():
        result = "✅ PASS"
    else:
        result = "❓ UNKNOWN"

    return {
        "run_id": run_dir.name,
        "branch": metadata.get("branch", "?"),
        "result": result,
        "attempts": f"{max_attempts}",
    }


def render_status_table(root: Path | None = None):
    console = Console()
    paths = get_project_paths(root)
    runs = paths["runs"]

    table = Table(title="📊 AI Cycle Run History")
    table.add_column("Run ID")
    table.add_column("Branch")
    table.add_column("Result")
    table.add_column("Attempts")

    if not runs.exists():
        console.print("[dim]No runs found. Run `ai-cycle run` first.[/dim]")
        return

    run_dirs = sorted([p for p in runs.iterdir() if p.is_dir()], reverse=True)
    if not run_dirs:
        console.print("[dim]No runs found. Run `ai-cycle run` first.[/dim]")
        return

    for run_dir in run_dirs:
        summary = _run_summary(run_dir)
        table.add_row(summary["run_id"], summary["branch"], summary["result"], summary["attempts"])

    console.print(table)


def render_run_details(run_id: str, root: Path | None = None):
    console = Console()
    paths = get_project_paths(root)
    run_dir = paths["runs"] / run_id

    if not run_dir.exists():
        console.print(f"[bold red][ERROR][/bold red] No such run: {run_id}")
        raise SystemExit(1)

    summary = _run_summary(run_dir)
    console.print(Panel(
        f"Run:    {summary['run_id']}\nBranch: {summary['branch']}\nResult: {summary['result']}\nAttempts: {summary['attempts']}",
        title="📋 Run Details",
        expand=False,
    ))

    for attempt_dir in sorted(run_dir.glob("attempt-*")):
        console.print(f"\n[bold]{attempt_dir.name}[/bold]")
        for fname in ("implementer.txt", "review-copilot.txt", "review-claude.txt", "validation.txt", "feedback.txt", "spec-questions.txt"):
            fpath = attempt_dir / fname
            if fpath.exists():
                console.print(f"  [dim]{fpath}[/dim]")

    terminal_feedback = run_dir / "terminal-feedback.txt"
    if terminal_feedback.exists():
        console.print(f"\n[bold red]Terminal feedback:[/bold red] {terminal_feedback}")
