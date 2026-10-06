import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.agents.codex import codex_plan_spec


class SpecPlannerTests(unittest.TestCase):
    def test_planner_is_read_only_and_returns_final_message(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            def fake_run(cmd, **kwargs):
                output = Path(cmd[cmd.index("--output-last-message") + 1])
                output.write_text("# Spec\n\n## Goal\nShip it.\n")
                self.assertIn("read-only", cmd)
                self.assertIn("PLAN MODE", kwargs["input_text"])
                self.assertIn("Hierarchy", kwargs["input_text"])
                self.assertIn("Odoo Technical Analyst", kwargs["input_text"])
                self.assertIn("## Field Specification", kwargs["input_text"])
                return subprocess.CompletedProcess(cmd, 0, "")

            with patch("ai_cycle.agents.codex.run", side_effect=fake_run):
                result = codex_plan_spec("Hierarchy", None, root)

            self.assertEqual(result, "# Spec\n\n## Goal\nShip it.\n")


if __name__ == "__main__":
    unittest.main()
