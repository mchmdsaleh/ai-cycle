from __future__ import annotations

import json
import re
import tempfile
from importlib.resources import files
from pathlib import Path

from ai_cycle.core.config import read, write
from ai_cycle.core.runner import die, require_commands, run

ARTIFACTS = ("proposal", "specs", "design", "wireframe", "tasks", "readiness")


def change_path(root: Path, change: str) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", change):
        die("Change name must be lowercase kebab-case, e.g. mandiri-payment-export.")
    path = root / "openspec" / "changes" / change
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        die("OpenSpec change must stay inside the repository.")
    return path


def openspec(root: Path, *args: str) -> str:
    require_commands(["openspec"])
    return run(["openspec", *args], cwd=root, check=True, quiet=True).stdout


def prepare_change(root: Path, change: str) -> Path:
    path = change_path(root, change)
    if not (root / "openspec").exists():
        openspec(root, "init", "--tools", "codex", "--no-animation")
    schema = files("ai_cycle").joinpath("openspec_schema")
    destination = root / "openspec" / "schemas" / "odoo-spec-driven"
    for resource in (schema.joinpath("schema.yaml"), *schema.joinpath("templates").iterdir()):
        relative = resource.name if resource.name == "schema.yaml" else f"templates/{resource.name}"
        target = destination / relative
        if not target.exists():
            write(target, resource.read_text(encoding="utf-8"))
    openspec(root, "schema", "validate", "odoo-spec-driven")
    if not path.exists():
        openspec(root, "new", "change", change, "--schema", "odoo-spec-driven")
    metadata = path / ".openspec.yaml"
    if not metadata.exists() or not re.search(r"^schema:\s*odoo-spec-driven\s*$", read(metadata), re.M):
        die("This change uses another schema. Use a new name for the Odoo workflow.")
    return path


def artifact_paths(path: Path) -> list[Path]:
    required = [path / name for name in ("proposal.md", "design.md", "wireframe.md", "tasks.md", "readiness.json")]
    specs = sorted((path / "specs").rglob("spec.md"))
    if not specs or any(not item.is_file() for item in required):
        die(f"Incomplete OpenSpec change: {path}. Run ai-cycle spec --change again.")
    for item in required + specs:
        if not item.resolve().is_relative_to(path.resolve()):
            die(f"Artifact escapes change directory: {item}")
    return required + specs


def load_change(root: Path, change: str, *, require_ready: bool = True) -> str:
    path = change_path(root, change)
    artifacts = artifact_paths(path)
    try:
        readiness = json.loads(read(path / "readiness.json"))
    except (ValueError, OSError) as error:
        die(f"Invalid readiness.json: {error}")
    if not isinstance(readiness, dict) or readiness.get("status") not in ("draft", "ready") or not isinstance(readiness.get("blockers"), list):
        die("readiness.json requires status draft/ready and a blockers list.")
    if require_ready and (readiness["status"] != "ready" or readiness["blockers"]):
        die(f"OpenSpec change is Draft or has blockers: {readiness['blockers']}. Resolve via ai-cycle spec --change {change}.")
    parts = []
    for item in artifacts:
        content = read(item)
        if item.name == "tasks.md":
            content = re.split(r"(?im)^## Implementation evidence[^\n]*(?:\n|$)", content, maxsplit=1)[0].rstrip() + "\n"
            content = re.sub(r"(?m)^(\s*-\s*)\[\s*[xX]\s*\]", r"\1[ ]", content)
        parts.append(f"## Artifact: {item.relative_to(path)}\n\n{content}")
    return "\n\n".join(parts)


def save_artifacts(path: Path, response: str):
    planning_dir = path.parents[2] / ".ai-cycle" / "planning" / path.name
    response_path = planning_dir / "planner-response.txt"
    write(response_path, response)
    try:
        if not response.strip():
            raise ValueError("planner response is empty")
        payload = json.loads(response)
        contents = payload["files"]
        if isinstance(contents, list):
            mapped = {}
            for item in contents:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str) or "content" not in item:
                    raise ValueError("files entries require path and content")
                if item["path"] in mapped:
                    raise ValueError(f"duplicate artifact path: {item['path']}")
                mapped[item["path"]] = item["content"]
            contents = mapped
        if not isinstance(contents, dict):
            raise ValueError("files must be an object or an array of path/content entries")
        existing_specs = sorted((path / "specs").rglob("spec.md"))
        preserved_specs = {}
        for item in existing_specs:
            name = str(item.relative_to(path))
            if name not in contents:
                preserved_specs[name] = item.read_text(encoding="utf-8")
                contents[name] = preserved_specs[name]
        required = {"proposal.md", "design.md", "wireframe.md", "tasks.md", "readiness.json"}
        if not required.issubset(contents) or not any(re.fullmatch(r"specs/(?:[a-z0-9-]+/)+spec\.md", name) for name in contents):
            raise ValueError("missing required artifacts")
        for name, content in contents.items():
            if name not in required and not re.fullmatch(r"specs/(?:[a-z0-9-]+/)+spec\.md", name):
                raise ValueError(f"unexpected artifact path: {name}")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"empty artifact: {name}")
            if not (path / name).resolve().is_relative_to(path.resolve()):
                raise ValueError(f"artifact escapes change directory: {name}")
        existing = {str(item.relative_to(path)) for item in (path / "specs").rglob("spec.md")}
        if not existing.issubset(contents):
            raise ValueError("revision must retain all existing capability specs")
        readiness = json.loads(contents["readiness.json"])
        if not isinstance(readiness, dict) or readiness.get("status") not in ("draft", "ready") or not isinstance(readiness.get("blockers"), list):
            raise ValueError("invalid readiness status/blockers")
        if readiness["status"] == "ready" and readiness["blockers"]:
            raise ValueError("ready change cannot have blockers")
    except (ValueError, TypeError, KeyError) as error:
        try:
            json.loads(response)
        except (ValueError, TypeError):
            pass
        else:
            write(planning_dir / "rejected-artifacts.json", response)
        die(f"Planner returned invalid OpenSpec artifacts: {error}. Raw response saved at {response_path}. Existing artifacts were not replaced.")
    with tempfile.TemporaryDirectory(prefix="ai-cycle-openspec-validate-") as temporary:
        root = Path(temporary)
        staged = root / "openspec" / "changes" / path.name
        for name, content in contents.items():
            write(staged / name, content.rstrip() + "\n")
        try:
            openspec(root, "validate", path.name, "--strict")
        except SystemExit:
            candidate = path.parents[2] / ".ai-cycle" / "planning" / path.name / "rejected-artifacts.json"
            write(candidate, json.dumps({"files": contents}, ensure_ascii=False, indent=2))
            die(f"OpenSpec validation failed. Existing artifacts were not replaced. Planner output saved at {candidate}")
    for name, content in contents.items():
        if name not in preserved_specs:
            write(path / name, content.rstrip() + "\n")
