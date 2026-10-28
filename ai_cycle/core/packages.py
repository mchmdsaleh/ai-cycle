from __future__ import annotations

import re
from pathlib import Path

from ai_cycle.core.config import read
from ai_cycle.core.openspec import change_path
from ai_cycle.core.runner import die

MAX_PACKAGE_CONTEXT_BYTES = 96_000


def package_context(root: Path, change: str, package: str, inventory: list[dict]) -> tuple[str, list[dict]]:
    if not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+)*", package):
        die("Package must name an existing capability under specs/, not a file path.")
    relative = f"specs/{package}/spec.md"
    selected = [item for item in inventory if item["path"] == relative]
    if not selected:
        choices = sorted({str(Path(item['path']).parent.relative_to('specs')) for item in inventory})
        die(f"Unknown package {package}. Available: {', '.join(choices)}")
    directory = change_path(root, change)
    parts = [f"""WORK PACKAGE: {package}
Only the selected capability requirements are implementation/review scope.
Proposal, design and wireframe below are shared constraints, not permission to
implement or reject unrelated capability requirements. Preserve existing behavior
outside this package and inspect affected dependency contracts before editing.
If a dependency needs a material product decision, report the precise blocker.
This package cannot establish acceptance of the full change; integration remains.
Tasks reference: {directory / 'tasks.md'} (inspect only relevant task sections).
The complete master spec remains in the repository; do not remove other scope.
"""]
    for name in ("proposal.md", "design.md", "wireframe.md", relative):
        parts.append(f"## Artifact: {name}\n\n{read(directory / name)}")
    context = "\n\n".join(parts)
    if len(context.encode('utf-8')) > MAX_PACKAGE_CONTEXT_BYTES:
        die(f"Package context exceeds {MAX_PACKAGE_CONTEXT_BYTES} bytes. Split the capability/shared design explicitly; no requirements were truncated.")
    return context, selected
