from __future__ import annotations

import shlex
import shutil
import subprocess

from rich.console import Console

console = Console()


def die(msg: str, code: int = 1):
    console.print(f"[bold red][ERROR][/bold red] {msg}")
    raise SystemExit(code)


def require_commands(names: list[str]):
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        die("Missing required command(s): " + ", ".join(missing))


def run(cmd, *, cwd=None, input_text=None, timeout=1800, env=None, check=False, quiet=False):
    """Run a subprocess with rich-formatted echo of the command line."""
    if not quiet:
        console.print(f"[dim]$ {' '.join(shlex.quote(str(x)) for x in cmd)}[/dim]")
    proc = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        env=env,
    )
    if check and proc.returncode != 0:
        console.print(proc.stdout)
        die(f"Command failed with exit code {proc.returncode}: {cmd[0]}")
    return proc
