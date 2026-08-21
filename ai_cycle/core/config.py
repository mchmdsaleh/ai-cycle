from __future__ import annotations

import json
from pathlib import Path

from ai_cycle.core.runner import die

DEFAULT_CONFIG = {
    "max_attempts": 2,
    "validation_commands": [],
}

DEFAULT_RULES = """# Permanent Rules

Add durable engineering rules here. These are enforced on every cycle,
in addition to the spec for the current task.
"""

DEFAULT_SPEC = """# Spec

Describe the task for the implementer here: goal, constraints, and
acceptance criteria.
"""


def get_project_paths(root: Path | None = None) -> dict[str, Path]:
    root = root or Path.cwd()
    state = root / ".ai-cycle"
    runs = state / "runs"
    return {"root": root, "state": state, "runs": runs}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_config(state: Path) -> dict:
    p = state / "config.json"
    if not p.exists():
        die(f"Missing {p}.")
    return json.loads(read(p))


def initialize_project(root: Path | None = None):
    """Create .ai-cycle/ with template spec.md, RULES.md, and config.json."""
    paths = get_project_paths(root)
    state = paths["state"]

    config_path = state / "config.json"
    spec_path = state / "spec.md"
    rules_path = state / "RULES.md"

    created = []
    if not config_path.exists():
        write(config_path, json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
        created.append(config_path)
    if not spec_path.exists():
        write(spec_path, DEFAULT_SPEC)
        created.append(spec_path)
    if not rules_path.exists():
        write(rules_path, DEFAULT_RULES)
        created.append(rules_path)

    (paths["runs"]).mkdir(parents=True, exist_ok=True)

    return created
