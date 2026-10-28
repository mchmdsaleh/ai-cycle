from __future__ import annotations

import subprocess
import json
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.live import Live

from ai_cycle.agents.claude import claude_review
from ai_cycle.agents.codex import codex_implement
from ai_cycle.agents.postmortem import propose_rule
from ai_cycle.core.config import get_project_paths, load_config, read, write
from ai_cycle.core.git import assert_clean_worktree, assert_git_repo, current_branch, get_diff
from ai_cycle.core.runner import die, require_commands
from ai_cycle.core.verdict import parse_verdict, review_json
from ai_cycle.resume import load_previous_feedback, sha256_text
from ai_cycle.ui.panels import render_header, render_verdict_table
from ai_cycle.ui.progress import CycleProgress
from ai_cycle.core.completion import requirement_inventory, inspect_completion, review_completion, pending_tasks, source_status, work_queue, select_target

MAX_REVIEW_DIFF_BYTES = 1_000_000


def build_feedback(claude: str, validation_log: str | None = None) -> str:
    parts = []
    if claude and parse_verdict(claude) != "PASS":
        parts.append("CLAUDE CODE REVIEW:\n" + compact_review(claude))
    if validation_log:
        parts.append("VALIDATION OUTPUT:\n" + validation_log)
    return "\n\n".join(parts)


def compact_review(text: str) -> str:
    """Return the structured reviewer JSON when present; it is enough for retries."""
    try:
        if "```json" in text:
            return json.dumps(json.loads(text.split("```json")[1].split("```")[0].strip()), indent=2)
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            return json.dumps(json.loads(text[start : end + 1]), indent=2)
    except Exception:
        pass
    return text.strip()


def run_validation(commands: list[str], run_dir: Path, cwd: Path, progress=None) -> bool:
    from ai_cycle.core.runner import run as run_cmd

    logs = []
    ok = True
    for index, raw in enumerate(commands, 1):
        cmd = ["bash", "-lc", raw]
        log_path = run_dir / f"validation-command-{index}.txt"
        if progress:
            progress.log_path = log_path
        p = run_cmd(cmd, cwd=cwd, timeout=1800, output_path=log_path)
        logs.append(f"$ {raw}\n{p.stdout}\n[exit={p.returncode}]\n")
        if p.returncode != 0:
            ok = False
    write(run_dir / "validation.txt", "\n".join(logs))
    return ok


def execute_cycle(
    resume: bool = False,
    allow_dirty: bool = False,
    max_attempts: int | None = None,
    root: Path | None = None,
    change: str | None = None,
    implementer: str | None = None,
    package: str | None = None,
):
    console = Console()
    root = root or Path.cwd()
    if package and not change:
        die("--package requires --change.")
    paths = get_project_paths(root)
    state, runs = paths["state"], paths["runs"]

    require_commands(["git", "bash"])
    assert_git_repo(root)
    assert_clean_worktree(root, allow_dirty)

    branch = current_branch(root)

    cfg = load_config(state)
    implementer = implementer or cfg.get("implementer", "codex")
    if implementer not in ("codex", "agy"):
        die("Unknown implementer. Choose codex or agy.")
    require_commands([implementer, "claude"] + (["codex"] if cfg.get("postmortem", False) and implementer != "codex" else []))
    implementer_stage = "🔧 Antigravity Implementer" if implementer == "agy" else "🔧 Codex Implementer"
    max_attempts = max_attempts or int(cfg.get("max_attempts", 2))
    validation_commands = cfg.get("validation_commands", [])
    base_branch = cfg.get("base_branch")
    review_model = cfg.get("review_model")

    spec_path = state / "spec.md"
    rules_path = state / "RULES.md"
    if (not change and not spec_path.exists()) or not rules_path.exists():
        die("Missing .ai-cycle/spec.md or .ai-cycle/RULES.md")

    if change:
        from ai_cycle.core.openspec import change_path, load_change, openspec
        spec = load_change(root, change)
        openspec(root, "validate", change, "--strict")
        task_path = change_path(root, change) / "tasks.md"
    else:
        spec = read(spec_path)
        task_path = None
    inventory = requirement_inventory(root, change) if change else None
    global_inventory = inventory
    execution_spec = spec
    if package:
        from ai_cycle.core.packages import package_context
        execution_spec, inventory = package_context(root, change, package, inventory)
        package_commands = cfg.get("package_validation_commands", {})
        if not isinstance(package_commands, dict):
            die("package_validation_commands must map capability names to command lists.")
        validation_commands = package_commands.get(package, validation_commands)
        if not isinstance(validation_commands, list) or any(not isinstance(command, str) for command in validation_commands):
            die("Package validation must be a list of commands.")
    rules = read(rules_path)

    runs.mkdir(parents=True, exist_ok=True)
    run_id = subprocess.check_output(["date", "+%Y%m%d-%H%M%S"], text=True).strip()
    base_run = runs / run_id
    base_run.mkdir()

    metadata = {"branch": branch, "spec_hash": sha256_text(spec)}
    metadata["implementer"] = implementer
    if change:
        metadata["change"] = change
    if package:
        metadata["package"] = package
    write(base_run / "metadata.json", __import__("json").dumps(metadata, indent=2))
    write(base_run / "result.json", json.dumps({"status": "incomplete", "reason": "Run has not completed validation and review."}))
    write(base_run / "spec-snapshot.md", spec)
    if inventory is not None:
        write(base_run / "requirements.json", json.dumps(inventory, indent=2))
    if package:
        write(base_run / "global-requirements.json", json.dumps(global_inventory, indent=2))
        write(base_run / "package-context.md", execution_spec)

    feedback = None
    resume_info = None
    checkpoint_rows = []
    retry_target = None

    if resume:
        previous = load_previous_feedback(runs, current_run=base_run, spec=spec, branch=branch, package=package)
        if previous:
            feedback = previous["feedback"]
            resume_info = previous["run"].name
            write(base_run / "resumed-from.txt", str(previous["run"]))
            attempts = sorted((path for path in previous["run"].glob("attempt-*") if path.name.removeprefix("attempt-").isdigit()), key=lambda path: int(path.name.removeprefix("attempt-")))
            # Only the latest attempt is current; do not resurrect older completion claims.
            if inventory is not None and attempts:
                # An agent that failed to start still has its incoming checkpoint.
                report_name = "completion.json" if (attempts[-1] / "completion.json").exists() else "checkpoint.json"
                previous_target = None
                target_path = attempts[-1] / "target.json"
                if report_name == "completion.json" and target_path.exists():
                    previous_target_data = json.loads(target_path.read_text())
                    if isinstance(previous_target_data, dict):
                        previous_target = previous_target_data.get("id")
                _, context, rows = inspect_completion(
                    root, attempts[-1], inventory, report_name=report_name,
                    target_id=previous_target,
                )
                if context and previous_target:
                    old_check_path = attempts[-1] / "completion-check.json"
                    if old_check_path.exists():
                        old_issues = json.loads(old_check_path.read_text()).get("issues", [])
                        if any("coverage must contain every active requirement ID" in issue
                               for issue in old_issues):
                            next_item = select_target(inventory, rows)
                            feedback = (
                                "Recovered the prior target-scoped completion report; its source evidence is retained. "
                                + (f"Continue with {next_item['id']}." if next_item else
                                   "All source targets are complete; continue with pending validation/review.")
                            )
                if not context and report_name == "completion.json" and (attempts[-1] / "checkpoint.json").exists():
                    _, context, rows = inspect_completion(root, attempts[-1], inventory, report_name="checkpoint.json")
                    if context:
                        console.print("Previous report rejected; resuming from its incoming checkpoint after rechecking source references.", markup=False)
                        feedback = ("Previous completion report was rejected. Use this attempt's checkpoint.json as the baseline; "
                                    "historical completion claims in the feedback are not current source findings.\n" + feedback)
                if context:
                    checkpoint_rows = rows
        else:
            console.print("[yellow][INFO][/yellow] No compatible failed run found to resume.")

    render_header(console, branch, metadata["spec_hash"], resume_info)
    if package:
        console.print(f"Package: {package} ({len(inventory)}/{len(global_inventory)} requirements). Full-change acceptance is not evaluated by this run.", markup=False)

    for attempt in range(1, max_attempts + 1):
        console.rule(f"ATTEMPT {attempt}/{max_attempts}")
        run_dir = base_run / f"attempt-{attempt}"
        run_dir.mkdir()
        target = (retry_target or select_target(inventory, checkpoint_rows)) if inventory is not None else None
        if inventory is not None:
            write(run_dir / "checkpoint.json", json.dumps({"requirements": checkpoint_rows}, indent=2))
            write(run_dir / "work-items.json", json.dumps(work_queue(inventory, checkpoint_rows), indent=2))
            write(run_dir / "target.json", json.dumps(target, indent=2))
            if target:
                console.print(f"Required target: {target['id']}", markup=False)

        progress = CycleProgress(console)
        if package:
            progress.coverage_label = f"Package {package}"
        progress.add_stage(implementer_stage)
        if inventory is not None:
            progress.add_stage("Scope Coverage")
        progress.add_stage("✅ Validation")
        progress.add_stage("🔍 Claude Review")

        with Live(get_renderable=progress.render, console=console, refresh_per_second=4) as live:
            progress.start_stage(implementer_stage, run_dir / "implementer.txt")
            live.update(progress.render())
            try:
                if task_path:
                    codex_implement(execution_spec, rules, feedback, run_dir, root, task_path=task_path, implementer=implementer, inventory=inventory)
                else:
                    codex_implement(spec, rules, feedback, run_dir, root, implementer=implementer)
            except (SystemExit, subprocess.TimeoutExpired) as error:
                progress.complete_stage(implementer_stage, success=False)
                live.update(progress.render())
                issues, _, _ = inspect_completion(root, run_dir, inventory, checkpoint=checkpoint_rows,
                                                  target_id=target.get("id") if target else None) if inventory is not None else ([], "", [])
                feedback = f"IMPLEMENTER INTERRUPTED/FAILED ({type(error).__name__}). Existing changes must be preserved. Inspect {run_dir / 'implementer.txt'} before continuing.\n" + "\n".join(issues)
                write(run_dir / "completion-check.json", json.dumps({"issues": issues, "implementer_failed": True}, indent=2))
                write(base_run / "terminal-feedback.txt", feedback)
                write(base_run / "result.json", json.dumps({"status": "failed", "reason": feedback}))
                raise
            if change and load_change(root, change) != spec:
                progress.complete_stage(implementer_stage, success=False)
                live.update(progress.render())
                die("OpenSpec planning artifacts changed during implementation. Review the changes and re-run planning before continuing.")
            progress.complete_stage(implementer_stage)
            live.update(progress.render())

            if inventory is not None:
                progress.start_stage("Scope Coverage", run_dir / "completion.json")
            completion_issues, completion_context, validated_rows = inspect_completion(
                root, run_dir, inventory, checkpoint=checkpoint_rows,
                target_id=target.get("id") if target else None,
            ) if inventory is not None else ([], "", [])
            if completion_context:
                checkpoint_rows = validated_rows
            if inventory is not None and target and not completion_issues:
                target_row = next((row for row in checkpoint_rows if row["id"] == target["id"]), {})
                if source_status(target_row) == "implemented" and target_row.get("evidence"):
                    pending_rows = [row for row in checkpoint_rows
                                    if source_status(row) != "implemented" or not row.get("evidence")]
                    if pending_rows:
                        completion_issues.append(
                            f"Package source progress: {len(inventory) - len(pending_rows)}/{len(inventory)} implemented; "
                            f"next target is {pending_rows[0]['id']}."
                        )
            pending_verification = [row["id"] for row in checkpoint_rows if row.get("verification_status", "pending") != "passed"]
            if inventory is not None:
                write(run_dir / "verification-pending.json", json.dumps({"requirements": pending_verification}, indent=2))
            if inventory is not None:
                counts = Counter(source_status(row) for row in checkpoint_rows) if completion_context else {}
                progress.set_coverage(counts, len(inventory))
                progress.complete_stage("Scope Coverage", success=not completion_issues)
                live.update(progress.render())
                write(run_dir / "completion-check.json", json.dumps({"issues": completion_issues}, indent=2))
            if completion_issues:
                target_row = next((row for row in checkpoint_rows if target and row["id"] == target["id"]), {}) if completion_context else {}
                target_complete = bool(target_row and source_status(target_row) == "implemented" and target_row.get("evidence"))
                target_blocked = target is not None and not target_complete
                if target_complete:
                    retry_target = None
                feedback = "INCOMPLETE ACTIVE REQUIREMENTS:\n" + "\n".join(completion_issues)
                if target_blocked:
                    reason = target_row.get("reason") or "Completion report invalid/missing or target lacks source evidence; inspect completion-check.json."
                    target_result = {"id": target["id"], "source_status": source_status(target_row), "reason": reason,
                                     "resolution_options": target_row.get("resolution_options", [])}
                    write(run_dir / "target-result.json", json.dumps(target_result, indent=2))
                    retry_target = {**target, "previous_status": source_status(target_row), "reason": reason}
                    retry_notice = (f"Retry this same required target; attempt {attempt}/{max_attempts}. Use the current checkpoint, "
                                    "address the stated source gap, and do not switch to unrelated requirements.\n" if attempt < max_attempts else
                                    f"Required target remained incomplete after {max_attempts} attempts.\n")
                    feedback = f"REQUIRED TARGET INCOMPLETE: {target['id']}\n{reason}\n{retry_notice}" + feedback
                write(run_dir / "feedback.txt", feedback)
                write(base_run / "result.json", json.dumps({"status": "partial", "reason": feedback}))
                if attempt < max_attempts:
                    if target_blocked:
                        console.print(f"Target incomplete; retrying the same target on attempt {attempt + 1}/{max_attempts}.", markup=False)
                    else:
                        console.print("Required target completed; continuing with the next source gap.", markup=False)
                    continue
                write(base_run / "terminal-feedback.txt", feedback)
                if target_blocked:
                    console.print(f"Target remains incomplete: {target['id']}\nReason: {reason}", markup=False)
                    die(f"Required target incomplete after {max_attempts} attempts. See {run_dir / 'target-result.json'}")
                die(f"Implementation remains partial. See {run_dir / 'completion-check.json'}")
            diff = get_diff(root, base_branch, allow_empty=True) if inventory is not None else get_diff(root, base_branch)
            write(run_dir / "diff.patch", diff)
            diff_bytes = len(diff.encode("utf-8"))
            if diff_bytes > MAX_REVIEW_DIFF_BYTES:
                die(
                    f"Review diff is too large ({diff_bytes / 1_000_000:.1f} MB). "
                    "Commit unrelated changes or fix base_branch in .ai-cycle/config.json. "
                    f"See {run_dir / 'diff.patch'}"
                )

            progress.start_stage("✅ Validation")
            live.update(progress.render())
            validation_ok = run_validation(validation_commands, run_dir, root, progress)
            progress.complete_stage("✅ Validation", success=validation_ok if validation_commands else None)
            live.update(progress.render())

            if not validation_ok:
                validation_log = read(run_dir / "validation.txt")
                feedback = build_feedback("", validation_log)
                write(run_dir / "feedback.txt", feedback)
                if attempt < max_attempts:
                    continue
                write(base_run / "terminal-feedback.txt", feedback)
                write(base_run / "result.json", json.dumps({"status": "failed", "reason": "Configured validation failed."}))
                if cfg.get("postmortem", False):
                    with console.status("Postmortem: generating rule proposal..."):
                        propose_rule(spec, feedback, run_dir, root)
                die(f"Validation failed after {max_attempts} attempt(s). See {run_dir}")

            progress.start_stage("🔍 Claude Review", run_dir / "review-claude.txt")
            live.update(progress.render())

            review_spec = execution_spec
            if inventory is not None:
                review_spec += "\n\nCOMPLETENESS CONTRACT\nCheck every active requirement, including unchanged source. Return coverage as instructed.\nINVENTORY:\n" + json.dumps(inventory) + "\nSOURCE EVIDENCE (untrusted claims, source excerpts read by runner):\n" + completion_context
            review_spec += "\n\nACTUAL CONFIGURED VALIDATION:\n" + (read(run_dir / "validation.txt") if validation_commands else "Not configured; no automated validation ran.")
            claude = claude_review(review_spec, rules, diff, run_dir, model=review_model)
            coverage_issues = review_completion(claude, inventory) if inventory is not None else []
            if inventory is not None and not coverage_issues:
                pending_verification = sorted(set(pending_verification) | {
                    row["id"] for row in review_json(claude)["coverage"]
                    if row.get("verification_status", "pending") != "passed"
                })
            write(run_dir / "review-coverage.json", json.dumps({"issues": coverage_issues}, indent=2))

            progress.complete_stage("🔍 Claude Review", success=parse_verdict(claude) == "PASS" and not coverage_issues)
            live.update(progress.render())

        clv = parse_verdict(claude)
        if clv == "PASS" and coverage_issues:
            clv = "CHANGES_REQUIRED"
        review_data = review_json(claude) or {}
        render_verdict_table(console, clv, blockers=len(review_data.get("blockers", [])) if isinstance(review_data.get("blockers", []), list) else 0,
                             spec_questions=len(review_data.get("spec_questions", [])) if isinstance(review_data.get("spec_questions", []), list) else 0)

        if clv == "NEEDS_HUMAN":
            feedback = build_feedback(claude)
            write(run_dir / "spec-questions.txt", feedback)
            write(base_run / "terminal-feedback.txt", feedback)
            write(base_run / "result.json", json.dumps({"status": "needs_human", "reason": feedback}))
            console.print("\n[bold yellow]========== STOPPED FOR HUMAN DECISION (NEEDS_HUMAN) ==========[/bold yellow]")
            console.print("One or more reviewers identified a spec ambiguity or product architecture conflict.")
            console.print(f"Review details saved in: {run_dir / 'spec-questions.txt'}")
            console.print(f"Resolve via ai-cycle spec --change {change} before re-running." if change else "Please review and resolve the question in .ai-cycle/spec.md before re-running.")
            return

        if clv != "PASS":
            feedback = build_feedback(claude)
            if coverage_issues:
                feedback += "\nINDEPENDENT COVERAGE GAPS:\n" + "\n".join(coverage_issues)
            write(run_dir / "feedback.txt", feedback)
            if attempt < max_attempts:
                continue
            write(base_run / "terminal-feedback.txt", feedback)
            write(base_run / "result.json", json.dumps({"status": "partial" if coverage_issues else "failed", "reason": feedback}))
            if cfg.get("postmortem", False):
                with console.status("Postmortem: generating rule proposal..."):
                    propose_rule(spec, feedback, run_dir, root)
            die(f"Review failed after {max_attempts} attempt(s). See {run_dir}")

        outstanding = pending_tasks(task_path) if task_path else []
        if package:
            verification_complete = bool(validation_commands) and not pending_verification
            checkpoint = {"package": package, "branch": branch, "spec_hash": metadata["spec_hash"],
                          "requirements": checkpoint_rows, "review_verdict": "PASS",
                          "verification_complete": verification_complete, "integration_required": True,
                          "evidence_sha256": {ref["path"]: sha256_text(read(root / ref["path"]))
                                              for row in checkpoint_rows for ref in row.get("evidence", [])}}
            write(run_dir / "package-checkpoint.json", json.dumps(checkpoint, indent=2))
            write(base_run / "result.json", json.dumps({"status": "package_reviewed", "package": package,
                  "reason": "Package source reviewed; full-change integration and any pending runtime verification remain required.",
                  "verification_complete": verification_complete, "pending_verification": pending_verification,
                  "integration_required": True}, indent=2))
            write(base_run / "terminal-feedback.txt", f"Package {package} source reviewed. Preserve its source; continue pending verification or the next package. Full-change integration remains required.")
            console.rule("PACKAGE SOURCE REVIEW COMPLETE - INTEGRATION PENDING")
            console.print(f"Package checkpoint: {run_dir / 'package-checkpoint.json'}. Verification complete: {verification_complete}. Not full-change PASS.")
        elif outstanding or not validation_commands or pending_verification:
            write(base_run / "result.json", json.dumps({"status": "awaiting_verification", "reason": "Source coverage reviewed; tasks or automated validation remain unverified.", "pending_tasks": outstanding, "pending_verification": pending_verification, "validation_configured": bool(validation_commands)}, indent=2))
            console.rule("SOURCE REVIEW COMPLETE - VERIFICATION PENDING")
            console.print(f"Source review passed, but {len(outstanding)} task(s) remain unchecked and {len(pending_verification)} requirement(s) await verification; automated validation configured: {bool(validation_commands)}. Not full acceptance.")
        else:
            write(base_run / "result.json", json.dumps({"status": "passed", "reason": "Validation, independent review and applicable completion gate passed; human acceptance remains."}))
            console.rule("HUMAN ACCEPTANCE GATE")
            console.print("Automated cycle passed." if validation_commands else "Code review passed. Automated validation is not configured.")
        console.print("Review the actual behavior and git diff yourself:")
        console.print("  git diff")
        console.print(f"  cat {run_dir / 'review-claude.txt'}")
        console.print(f"  cat {run_dir / 'validation.txt'}")
        console.print("\nNo commit or push was performed.")
        return
