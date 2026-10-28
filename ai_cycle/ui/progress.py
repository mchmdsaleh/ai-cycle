from __future__ import annotations

import json
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
    "not configured": "-",
}


def _format_log_line(line: str) -> str:
    try:
        event = json.loads(line)
    except (TypeError, ValueError):
        return line
    if not isinstance(event, dict):
        return line
    if event.get("event") == "step_update":
        step = event.get("step_update", {})
        if not isinstance(step, dict):
            return "Agy step update"
        delta = step.get("text_delta")
        if isinstance(delta, str) and delta:
            return delta.strip() or "Agent is responding..."
        if step.get("step_type") == "tool":
            name = step.get("tool_name", "tool")
            info = step.get("tool_info", {})
            if not isinstance(info, dict):
                info = {}
            parameters = info.get("parameters", {})
            target = ""
            if isinstance(parameters, dict):
                target = next((Path(str(value)).name for key, value in parameters.items()
                               if key.lower() in {"path", "filepath", "filename"} and value), "")
            output = info.get("output", step.get("output", ""))
            summary = next((line.strip() for line in reversed(str(output).splitlines())
                            if line.strip()), "")
            if summary.startswith("Command output:"):
                summary = ""
            details = target or summary
            state = step.get("state", "running").lower()
            return f"Agy {name}: {details or state}"[-160:]
        return f"Agy {step.get('step_type', 'step')}: {step.get('state', 'running')}"
    if event.get("event") == "result":
        result = event.get("result", {})
        return f"Agy {result.get('status', 'finished')}"
    if event.get("event") == "init":
        return "Agy session started"
    return line


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
        self.coverage_summary: str | None = None
        self.coverage_label = "Scope Coverage"

    def set_coverage(self, counts: dict[str, int], total: int):
        implemented = counts.get("implemented", 0)
        percentage = implemented / total * 100 if total else 0
        self.coverage_summary = (
            f"{self.coverage_label} (agent report): {implemented}/{total} implemented ({percentage:.0f}%)\n"
            f"Partial: {counts.get('partial', 0)} | Missing: {counts.get('missing', 0)} | "
            f"Unverified: {counts.get('unverified', 0)}"
        )
        unreported = total - sum(counts.values())
        if not counts and total:
            self.coverage_summary = f"{self.coverage_label}: report unavailable (missing/invalid)"
        if unreported:
            self.coverage_summary += f" | Unreported: {unreported}"
        if not self.console.is_terminal:
            self.console.print(self.coverage_summary, markup=False)

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

    def complete_stage(self, name: str, success: bool | None = True):
        self.stages[name] = "not configured" if success is None else ("done" if success else "failed")
        started = self.start_times.get(name)
        if started is not None:
            self.durations[name] = time.monotonic() - started

    def render(self) -> Table:
        table = Table(title="Cycle Progress")
        table.add_column("Stage")
        table.add_column("Status")
        table.add_column("Duration")
        caption = [self.coverage_summary] if self.coverage_summary else []
        if self.log_path:
            last_output = "Waiting for output (agent may buffer until completion)"
            try:
                with self.log_path.open("rb") as log:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell() - 4096))
                    lines = log.read().decode("utf-8", errors="replace").splitlines()
                if lines:
                    last_output = next((_format_log_line(line)[-160:] for line in reversed(lines)
                                        if line.strip()), last_output)
            except FileNotFoundError:
                pass
            caption.append(f"Log: {self.log_path}")
            if self.log_path.name != "completion.json" or not self.coverage_summary:
                caption.append(last_output)
        if caption:
            table.caption = Text("\n".join(caption))
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
