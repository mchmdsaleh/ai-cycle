from __future__ import annotations

import json
import re
from pathlib import Path


def requirement_inventory(root: Path, change: str) -> list[dict]:
    from ai_cycle.core.openspec import change_path

    directory = change_path(root, change)
    inventory = []
    for path in sorted((directory / "specs").rglob("spec.md")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?m)^### Requirement:\s*(.+)$", text):
            title = match.group(1).strip()
            relative = str(path.relative_to(directory))
            inventory.append({"id": f"{relative}::{title}", "path": relative,
                              "line": text.count("\n", 0, match.start()) + 1})
    if not inventory or len({r['id'] for r in inventory}) != len(inventory):
        raise ValueError("OpenSpec requires nonempty, unique requirement IDs.")
    return inventory


def inspect_completion(root: Path, run_dir: Path, inventory: list[dict], *, report_name: str = "completion.json", checkpoint: list[dict] | None = None, target_id: str | None = None) -> tuple[list[str], str, list[dict]]:
    """Validate coverage identity and read bounded, real source evidence for the reviewer."""
    issues, excerpts, seen = [], [], set()
    try:
        path = run_dir / report_name
        if path.stat().st_size > 1_000_000:
            raise ValueError("completion.json exceeds 1 MB")
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["requirements"]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("requirements must be an array of objects")
        expected = {item["id"] for item in inventory}
        ids = [row.get("id") for row in rows]
        if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or not set(ids) <= expected:
            raise ValueError("coverage contains duplicate or unknown requirement IDs")
        if target_id is None and set(ids) != expected:
            raise ValueError("coverage must contain every active requirement ID exactly once, without extras")
        if target_id is not None and target_id not in ids:
            raise ValueError(f"targeted completion report must include its assigned requirement: {target_id}")
        if report_name == "completion.json":
            # Compare against the runner's incoming snapshot, never an agent-selected old run.
            if checkpoint is None and (run_dir / "checkpoint.json").exists():
                checkpoint = json.loads((run_dir / "checkpoint.json").read_text())["requirements"]
            if checkpoint is not None:
                if not isinstance(checkpoint, list) or any(not isinstance(row, dict) for row in checkpoint):
                    raise ValueError("invalid incoming checkpoint")
                if any(row.get("id") not in expected for row in checkpoint):
                    raise ValueError("incoming checkpoint contains an unknown requirement ID")
                checkpoint_ids = [row["id"] for row in checkpoint]
                if len(set(checkpoint_ids)) != len(checkpoint_ids):
                    raise ValueError("incoming checkpoint contains duplicate requirement IDs")
                previous = {row["id"]: row for row in checkpoint}
                rank = {"unverified": 0, "missing": 1, "partial": 2, "implemented": 3}
                for row in rows:
                    before = source_status(previous.get(row["id"], {}))
                    after = source_status(row)
                    if rank.get(before, -1) > rank.get(after, -1):
                        reassessment = row.get("reassessment", {})
                        if (not isinstance(reassessment, dict)
                                or reassessment.get("previous_status") != before
                                or not isinstance(reassessment.get("reason"), str)
                                or not reassessment["reason"].strip()
                                or not row.get("evidence")):
                            raise ValueError(
                                f"Unexplained checkpoint downgrade for {row['id']}: {before} -> {after}. "
                                "Use this attempt's checkpoint.json; provide reassessment.previous_status, "
                                "reassessment.reason explaining the new source finding, and current source evidence."
                            )
                if target_id is not None:
                    updated = {row["id"]: row for row in rows}
                    merged = {
                        item["id"]: previous.get(item["id"], {
                            "id": item["id"], "source_status": "unverified",
                            "reason": "Not assessed yet; queued for a later target.",
                            "verification_status": "pending", "evidence": [],
                        })
                        for item in inventory
                    }
                    merged.update(updated)
                    rows = [merged[item["id"]] for item in inventory]
            elif target_id is not None:
                updated = {row["id"]: row for row in rows}
                rows = [updated.get(item["id"], {
                    "id": item["id"], "source_status": "unverified",
                    "reason": "Not assessed yet; queued for a later target.",
                    "verification_status": "pending", "evidence": [],
                }) for item in inventory]
        submitted_ids = set(ids)
        validated_rows = []
        for original in rows:
            row = dict(original)
            identifier = row['id']
            row_excerpts = []
            row_evidence = set()
            try:
                status = source_status(row)
                if status not in ("implemented", "partial", "missing", "unverified"):
                    raise ValueError("invalid source status")
                evidence = row.get("evidence", [])
                if not isinstance(evidence, list) or len(evidence) > 8:
                    raise ValueError("invalid evidence list")
                if status == "implemented" and not evidence:
                    raise ValueError("implemented without source evidence")
                row_excerpts.append(f"Requirement {identifier}\nClaim (untrusted): {json.dumps(row, ensure_ascii=False)}")
                for ref in evidence:
                    if not isinstance(ref, dict):
                        raise ValueError("evidence reference must be an object")
                    relative, start, end = ref["path"], ref["line"], ref["end_line"]
                    file = root / relative
                    if not isinstance(relative, str) or Path(relative).is_absolute() or not file.resolve().is_relative_to(root.resolve()):
                        raise ValueError("evidence must stay inside the repository")
                    if set(file.relative_to(root).parts) & {".git", ".ai-cycle", "openspec", ".agents"} or file.suffix in (".conf", ".json") or file.name.startswith(".env"):
                        raise ValueError("planning, configuration and private state are not source evidence")
                    if type(start) is not int or type(end) is not int or start < 1 or end < start or end - start >= 120:
                        raise ValueError("evidence requires a valid range of at most 120 lines")
                    if not file.is_file() or file.stat().st_size > 1_000_000:
                        raise ValueError(f"missing or oversized source evidence: {relative}")
                    lines = file.read_text(encoding="utf-8").splitlines()
                    if end > len(lines):
                        raise ValueError(f"evidence line is outside {relative}")
                    key = (relative, start, end)
                    if key not in seen and key not in row_evidence:
                        row_excerpts.append(f"Source {relative}:{start}\n" + "\n".join(f"{i + start}: {line}" for i, line in enumerate(lines[start - 1:end])))
                    row_evidence.add(key)
                verification = row.get("verification_status", "pending")
                if verification not in ("passed", "failed", "pending"):
                    row["verification_status"] = "pending"
                    row["verification_reason"] = "Invalid verification status in report; treated as pending."
                    issues.append(f"{identifier}: invalid verification status; treated as pending")
            except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
                row["source_status"] = "unverified"
                if "status" in row:
                    row["status"] = "unverified"
                row["reason"] = f"Invalid source evidence; recheck this requirement: {error}"
                row["verification_status"] = "pending"
                if target_id is None or identifier in submitted_ids:
                    issues.append(f"{identifier}: invalid source evidence: {error}")
                row_excerpts = [f"Requirement {identifier}\nSource status unverified: {error}"]
                row_evidence.clear()
            seen.update(row_evidence)
            validated_rows.append(row)
            excerpts.extend(row_excerpts)
            if source_status(row) != "implemented" and (target_id is None or identifier in submitted_ids):
                issues.append(f"{identifier}: {source_status(row)}: {row.get('reason', '')}")
        context = "\n\n".join(excerpts)
        if len(context.encode()) > 500_000:
            raise ValueError("Source evidence exceeds 500 KB; use focused, nonduplicated ranges")
        return issues, context, validated_rows
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        return [f"Completion report invalid/missing: {error}"], "", []


def review_completion(text: str, inventory: list[dict]) -> list[str]:
    from ai_cycle.core.verdict import review_json

    data = review_json(text)
    rows = data.get("coverage") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return ["Independent review must provide coverage for every active requirement."]
    expected = {row["id"] for row in inventory}
    ids = [row.get("id") for row in rows]
    if any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or set(ids) != expected:
        return ["Independent review coverage omitted, duplicated or invented requirement IDs."]
    try:
        return [f"{row['id']}: {source_status(row)}: {row.get('reason', '')}"
                for row in rows if source_status(row) != "implemented"]
    except ValueError as error:
        return [str(error)]


def source_status(row: dict) -> str | None:
    if "source_status" in row and "status" in row and row["source_status"] != row["status"]:
        raise ValueError("Conflicting status/source_status; report source completion separately from verification")
    return row.get("source_status", row.get("status"))


def work_queue(inventory: list[dict], rows: list[dict]) -> list[dict]:
    """Group unfinished source by capability; checkpoint claims still need review."""
    previous = {row["id"]: row for row in rows}
    groups = {}
    for item in inventory:
        group = groups.setdefault(item["path"], {"capability": item["path"], "pending": [], "source_complete": []})
        row = previous.get(item["id"], {})
        complete = source_status(row) == "implemented" and bool(row.get("evidence"))
        group["source_complete" if complete else "pending"].append(item["id"])
    return list(groups.values())


def pending_tasks(path: Path) -> list[str]:
    text = re.split(r"(?im)^## Implementation evidence[^\n]*$", path.read_text(encoding="utf-8"), maxsplit=1)[0]
    return [description for marker, description in re.findall(r"(?m)^\s*-\s*\[([^\]\n]*)\]\s+(.+)$", text)
            if marker.strip().lower() != "x"]


def select_target(inventory: list[dict], rows: list[dict]) -> dict | None:
    previous = {row["id"]: row for row in rows}
    candidates = []
    priorities = {"missing": 0, "partial": 1, "unverified": 2}
    for item in inventory:
        row = previous.get(item["id"], {})
        status = source_status(row)
        if status == "implemented" and row.get("evidence"):
            continue
        candidates.append((priorities.get(status, 3), item, row))
    if not candidates:
        return None
    _, item, row = min(candidates, key=lambda candidate: candidate[0])
    return {**item, "previous_status": source_status(row), "reason": row.get("reason", "No source checkpoint yet; inspect this requirement first.")}
