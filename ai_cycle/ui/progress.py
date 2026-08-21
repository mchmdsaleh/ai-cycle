from __future__ import annotations

import time

from rich.table import Table

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

    def add_stage(self, name: str):
        if name not in self.stages:
            self.order.append(name)
        self.stages[name] = "pending"

    def start_stage(self, name: str):
        self.add_stage(name)
        self.stages[name] = "running"
        self.start_times[name] = time.time()

    def complete_stage(self, name: str, success: bool = True):
        self.stages[name] = "done" if success else "failed"
        started = self.start_times.get(name)
        if started is not None:
            self.durations[name] = time.time() - started

    def render(self) -> Table:
        table = Table(title="Cycle Progress")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Duration")
        for name in self.order:
            status = self.stages.get(name, "pending")
            if status == "running":
                elapsed = time.time() - self.start_times.get(name, time.time())
            else:
                elapsed = self.durations.get(name)
            icon = _ICONS.get(status, "⏳")
            duration_str = f"{elapsed:.0f}s" if elapsed is not None else "—"
            table.add_row(name, f"{icon} {status}", duration_str)
        return table
