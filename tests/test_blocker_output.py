import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner
from ai_cycle.cli import app


class BlockerOutputTests(unittest.TestCase):
    def test_spec_displays_decision_options_instead_of_entire_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            change = root / "openspec/changes/example"
            change.mkdir(parents=True)
            (change / "proposal.md").write_text("# Proposal\n## Open Questions\n### D1 - Department\nMengapa Memblokir: quota berbeda.\n#### D1.1 - Pilih department\n- A: Requester\n- B: Creator\n## Impact\nNot part of the question display.\n")
            (change / "readiness.json").write_text(json.dumps({"status": "draft", "blockers": [{"id": "D1", "question": "Department?"}], "internalMetadata": "do-not-dump"}))
            with patch("pathlib.Path.cwd", return_value=root), patch("ai_cycle.core.runner.require_commands"), patch("ai_cycle.core.git.assert_git_repo"), patch("ai_cycle.core.config.initialize_project"), patch("ai_cycle.core.openspec.prepare_change", return_value=change), patch("ai_cycle.core.openspec.openspec", return_value="{}"), patch("ai_cycle.core.openspec.save_artifacts"), patch("ai_cycle.agents.codex.codex_plan_spec", return_value="{}"):
                result = CliRunner().invoke(app, ["spec", "Explain decisions", "--change", "example"])
            self.assertEqual(result.exit_code, 0, result.output)
            for expected in ("Active blockers: 1", "Mengapa Memblokir", "D1.1", "Requester", "Creator", "--change example"):
                self.assertIn(expected, result.output)
            self.assertNotIn("do-not-dump", result.output)
            self.assertNotIn("Not part of the question display", result.output)
