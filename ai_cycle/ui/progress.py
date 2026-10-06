from __future__ import annotations

import time
from pathlib import Path

from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

_ICONS = {
    "pending": "⏳",
    "running": "🔄",
    "done": "✅",
    "failed": "❌",
}


class CycleProgress:
    """Live-updating progress display for the cycle stages."""

    def __init__(self, console):
        self.console = console
        self.order: list[str] = []
        self.stages: dict[str, str] = {}
        self.start_times: dict[str, float] = {}
        self.durations: dict[str, float] = {}
        self.spinner = Spinner("dots", text="running")
        self.log_path: Path | None = None

    def add_stage(self, name: str):
        if name not in self.stages:
            self.order.append(name)
        self.stages[name] = "pending"

    def start_stage(self, name: str, log_path: Path | None = None):
        self.add_stage(name)
        self.stages[name] = "running"
        self.start_times[name] = time.monotonic()
        self.log_path = log_path
        if not self.console.is_terminal:
            self.console.print(f"Starting: {name}", markup=False)
            if log_path:
                self.console.print(f"Log: {log_path}", markup=False)

    def complete_stage(self, name: str, success: bool = True):
        self.stages[name] = "done" if success else "failed"
        started = self.start_times.get(name)
        if started is not None:
            self.durations[name] = time.monotonic() - started

    def render(self) -> Table:
        table = Table(title="Cycle Progress")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Duration")
        if self.log_path:
            last_output = "Waiting for output (agent may buffer until completion)"
            try:
                with self.log_path.open("rb") as log:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell() - 4096))
                    lines = log.read().decode("utf-8", errors="replace").splitlines()
                if lines:
                    last_output = lines[-1][-160:]
            except FileNotFoundError:
                pass
            table.caption = Text(f"Log: {self.log_path}\n{last_output}")
        for name in self.order:
            status = self.stages.get(name, "pending")
            if status == "running":
                elapsed = time.monotonic() - self.start_times[name]
            else:
                elapsed = self.durations.get(name)
            icon = _ICONS.get(status, "⏳")
            duration_str = f"{elapsed:.0f}s" if elapsed is not None else "—"
            table.add_row(name, self.spinner if status == "running" else f"{icon} {status}", duration_str)
        return table
