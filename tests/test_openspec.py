import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.core.openspec import change_path, load_change, save_artifacts
from ai_cycle.orchestrator import execute_cycle


def payload():
    return {"files": {
        "proposal.md": "# Proposal\n## Why\nExport payments.\n## What Changes\nAdd vendor payment CSV export.\n## Capabilities\n### New Capabilities\n- payment-export: CSV export\n## Impact\nPayment module.\n",
        "design.md": "# Design\nExisting payment model.\n",
        "wireframe.md": "# Wireframe\nNot applicable.\n",
        "tasks.md": "# Tasks\n- [ ] 1.1 Export and verify CSV.\n",
        "readiness.json": json.dumps({"status": "ready", "blockers": []}),
        "specs/payment-export/spec.md": "## Purpose\nAllow users to export vendor payments to the bank in a verified CSV format.\n\n## ADDED Requirements\n### Requirement: Export payments\nThe system SHALL export selected payments.\n#### Scenario: Export selected payments\n- **WHEN** user requests export\n- **THEN** a CSV is downloaded\n",
    }}


class OpenSpecTests(unittest.TestCase):
    def test_schema_array_is_saved_and_duplicate_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = change_path(Path(td), "payment-export")
            entries = [{"path": name, "content": content} for name, content in payload()["files"].items()]
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps({"files": entries}))
            before = (path / "proposal.md").read_text()
            entries.append({"path": "proposal.md", "content": "replacement"})
            with self.assertRaises(SystemExit):
                save_artifacts(path, json.dumps({"files": entries}))
            self.assertEqual((path / "proposal.md").read_text(), before)

    def test_omitted_existing_capability_specs_are_preserved_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            path = change_path(Path(td), "payment-export")
            second_spec = "specs/payment-approval/spec.md"
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps(payload()))
                (path / second_spec).parent.mkdir(parents=True)
                (path / second_spec).write_text("existing approval capability\n\n")

                revised = payload()
                revised["files"].pop(second_spec, None)
                save_artifacts(path, json.dumps(revised))

            self.assertEqual((path / second_spec).read_text(), "existing approval capability\n\n")

    def test_empty_planner_response_is_saved_and_existing_artifacts_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = change_path(root, "payment-export")
            path.mkdir(parents=True)
            (path / "design.md").write_text("existing design")

            with patch("ai_cycle.core.openspec.die", side_effect=SystemExit(1)) as die:
                with self.assertRaises(SystemExit):
                    save_artifacts(path, "")

            raw = root / ".ai-cycle/planning/payment-export/planner-response.txt"
            self.assertEqual(raw.read_text(), "")
            self.assertIn(str(raw), die.call_args.args[0])
            self.assertEqual((path / "design.md").read_text(), "existing design")

    def test_validation_and_traversal_leave_existing_artifacts_intact(self):
        with tempfile.TemporaryDirectory() as td:
            path = change_path(Path(td), "payment-export")
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps(payload()))
            before = (path / "design.md").read_text()
            bad = payload()
            bad["files"]["../outside.md"] = "bad"
            with self.assertRaises(SystemExit):
                save_artifacts(path, json.dumps(bad))
            with patch("ai_cycle.core.openspec.openspec", side_effect=SystemExit(1)):
                revised = payload()
                revised["files"]["design.md"] = "changed"
                with self.assertRaises(SystemExit):
                    save_artifacts(path, json.dumps(revised))
            self.assertEqual((path / "design.md").read_text(), before)
            saved = Path(td) / ".ai-cycle/planning/payment-export/rejected-artifacts.json"
            self.assertEqual(json.loads(saved.read_text())["files"]["design.md"], "changed")

    def test_gate_and_task_completion_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = change_path(root, "payment-export")
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps(payload()))
            initial = load_change(root, "payment-export")
            tasks = path / "tasks.md"
            tasks.write_text(tasks.read_text().replace("[ ]", "[x]"))
            self.assertEqual(initial, load_change(root, "payment-export"))
            tasks.write_text(tasks.read_text() + "\n\n## Implementation evidence — 2026-10-15\n\nParser checks passed; browser unavailable.\n")
            self.assertEqual(initial, load_change(root, "payment-export"))
            tasks.write_text(tasks.read_text().replace("Export and verify CSV", "Skip export checks"))
            self.assertNotEqual(initial, load_change(root, "payment-export"))
            (path / "readiness.json").write_text('{"status":"draft","blockers":["Eligible states?"]}')
            with self.assertRaises(SystemExit):
                load_change(root, "payment-export")
            with self.assertRaises(SystemExit):
                change_path(root, "../escape")

    def test_draft_stops_before_implementer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / ".ai-cycle"
            state.mkdir()
            (state / "config.json").write_text('{}')
            (state / "RULES.md").write_text('Rules')
            path = change_path(root, "payment-export")
            draft = payload()
            draft["files"]["readiness.json"] = '{"status":"draft","blockers":["D2 source?"]}'
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps(draft))
            with patch("ai_cycle.orchestrator.require_commands"), patch("ai_cycle.orchestrator.assert_git_repo"), patch("ai_cycle.orchestrator.assert_clean_worktree"), patch("ai_cycle.orchestrator.current_branch", return_value="main"), patch("ai_cycle.orchestrator.codex_implement") as implement:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change="payment-export")
                implement.assert_not_called()

    def test_ready_cycle_passes_artifacts_and_task_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / ".ai-cycle"
            state.mkdir()
            (state / "config.json").write_text('{}')
            (state / "RULES.md").write_text('Rules')
            path = change_path(root, "payment-export")
            with patch("ai_cycle.core.openspec.openspec"):
                save_artifacts(path, json.dumps(payload()))
                def complete(*args, **kwargs):
                    (root / "application.py").write_text("def export():\n    return 'csv'\n")
                    inventory = kwargs['inventory']
                    report = {"requirements": [{"id": row['id'], "status": "implemented", "evidence": [{"path": "application.py", "line": 1, "end_line": 2}]} for row in inventory]}
                    (args[3] / "completion.json").write_text(json.dumps(report))
                identifier = "specs/payment-export/spec.md::Export payments"
                verdict = json.dumps({"verdict": "PASS", "coverage": [{"id": identifier, "status": "implemented"}]})
                with patch("ai_cycle.orchestrator.require_commands"), patch("ai_cycle.orchestrator.assert_git_repo"), patch("ai_cycle.orchestrator.assert_clean_worktree"), patch("ai_cycle.orchestrator.current_branch", return_value="main"), patch("ai_cycle.orchestrator.codex_implement", side_effect=complete) as implement, patch("ai_cycle.orchestrator.get_diff", return_value="code diff"), patch("ai_cycle.orchestrator.claude_review", return_value=verdict) as reviewer:
                    execute_cycle(root=root, change="payment-export")
                    self.assertEqual(implement.call_args.kwargs["task_path"], path / "tasks.md")
                    self.assertIn("Artifact: specs/payment-export/spec.md", reviewer.call_args.args[0])
                    self.assertFalse((state / "spec.md").exists())
                    outcome = json.loads(next((state / "runs").glob("*/result.json")).read_text())
                    self.assertEqual(outcome['status'], 'awaiting_verification')
