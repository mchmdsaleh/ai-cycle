from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_cycle.core.config import read


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_previous_feedback(runs: Path, current_run: Path, spec: str, branch: str, *, package: str | None = None) -> dict | None:
    """Find the most recent prior run on the same branch/spec that has terminal feedback."""
    if not runs.exists():
        return None

    current_spec_hash = sha256_text(spec)

    previous_runs = sorted(
        [p for p in runs.iterdir() if p.is_dir() and p != current_run],
        reverse=True,
    )

    for run_dir in previous_runs:
        metadata_path = run_dir / "metadata.json"
        feedback_path = run_dir / "terminal-feedback.txt"

        if not metadata_path.exists() or not feedback_path.exists():
            continue

        try:
            metadata = json.loads(read(metadata_path))
        except Exception:
            continue

        # Prevent stale feedback crossing branches
        if metadata.get("branch") != branch:
            continue

        # Prevent feedback from an old spec
        if metadata.get("spec_hash") != current_spec_hash:
            continue
        if metadata.get("package") != package:
            continue

        return {
            "run": run_dir,
            "feedback": read(feedback_path),
        }

    return None
