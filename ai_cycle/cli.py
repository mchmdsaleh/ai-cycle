from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="ai-cycle",
    help="🤖 Multi-agent AI coding cycle orchestrator",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    resume: bool = typer.Option(False, help="Resume from latest failed run"),
    allow_dirty: bool = typer.Option(False, help="Allow dirty working tree"),
    max_attempts: Optional[int] = typer.Option(None, help="Override max attempts"),
):
    """🚀 Run the AI coding cycle"""
    from ai_cycle.orchestrator import execute_cycle

    execute_cycle(resume=resume, allow_dirty=allow_dirty, max_attempts=max_attempts)


@app.command()
def status():
    """📊 Show status of all runs"""
    from ai_cycle.ui.panels import render_status_table

    render_status_table()


@app.command()
def logs(run_id: str = typer.Argument(..., help="Run ID, e.g. 20260814-141321")):
    """📋 Show detailed logs for a specific run"""
    from ai_cycle.ui.panels import render_run_details

    render_run_details(run_id)


@app.command()
def init():
    """📁 Initialize .ai-cycle/ in current directory"""
    from ai_cycle.core.config import initialize_project

    created = initialize_project()
    if created:
        console.print("[green]Created:[/green]")
        for p in created:
            console.print(f"  {p}")
    else:
        console.print("[dim].ai-cycle/ already initialized.[/dim]")


worktree_app = typer.Typer(help="🌳 Manage git worktrees for parallel tasks")
app.add_typer(worktree_app, name="worktree")


@worktree_app.command("add")
def worktree_add(
    name: str,
    base: str = typer.Option("main", help="Base branch to branch from"),
    existing: bool = typer.Option(False, help="Use an existing branch instead of creating one"),
):
    """Create a new worktree with .ai-cycle/ template copied in"""
    from ai_cycle.core.config import get_project_paths, initialize_project
    from ai_cycle.core.git import worktree_add as git_worktree_add

    root = Path.cwd()
    target = git_worktree_add(root, name, base=base, existing=existing)

    src_state = get_project_paths(root)["state"]
    if src_state.exists():
        import shutil

        dst_state = target / ".ai-cycle"
        for fname in ("config.json", "RULES.md", "spec.md"):
            src_file = src_state / fname
            if src_file.exists():
                dst_state.mkdir(parents=True, exist_ok=True)
                shutil.copy(src_file, dst_state / fname)
    else:
        initialize_project(target)

    console.print(f"[green]Worktree created:[/green] {target}")
    console.print(f"Next: cd {target} && ai-cycle run")


@worktree_app.command("list")
def worktree_list_cmd():
    """List active worktrees and their cycle status"""
    from ai_cycle.core.git import worktree_list

    root = Path.cwd()
    entries = worktree_list(root)

    table = Table(title="🌳 Active Worktrees")
    table.add_column("Path")
    table.add_column("Branch")
    for entry in entries:
        if entry.get("bare"):
            continue
        table.add_row(entry.get("path", "?"), entry.get("branch", "?"))
    console.print(table)


@worktree_app.command("remove")
def worktree_remove_cmd(
    name: str,
    force: bool = typer.Option(False, help="Force removal even with uncommitted changes"),
):
    """Remove a worktree"""
    from ai_cycle.core.git import worktree_remove, worktrees_root

    root = Path.cwd()
    path = worktrees_root(root) / name
    worktree_remove(root, path, force=force)
    console.print(f"[green]Removed worktree:[/green] {path}")


if __name__ == "__main__":
    app()
