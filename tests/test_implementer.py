import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.agents.codex import codex_implement


class ImplementerTests(unittest.TestCase):
    def test_agy_receives_same_context_without_codex_gateway(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.dict(os.environ, {"NINEROUTER_API_KEY": "test-gateway-key"}), patch("ai_cycle.agents.codex.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "done")
                result = codex_implement("requirement", "rules", "fix feedback", root, root, task_path=root / "tasks.md", implementer="agy")
                args, kwargs = run.call_args
                self.assertEqual(args[0], ["agy", "--print", "--mode", "accept-edits", "--sandbox", "--output-format", "text"])
                self.assertEqual(kwargs["cwd"], root)
                self.assertEqual(kwargs["output_path"], root / "implementer.txt")
                for value in ("requirement", "rules", "fix feedback", str(root / "tasks.md")):
                    self.assertIn(value, kwargs["input_text"])
                self.assertNotEqual(kwargs["env"].get("OPENAI_API_KEY"), "test-gateway-key")
                self.assertEqual(result, "done")

    def test_default_and_failure(self):
        with tempfile.TemporaryDirectory() as td, patch("ai_cycle.agents.codex.run") as run:
            root = Path(td)
            run.return_value = subprocess.CompletedProcess([], 0, "done")
            codex_implement("spec", "rules", None, root, root)
            self.assertEqual(run.call_args.args[0][0:2], ["codex", "exec"])
            run.return_value = subprocess.CompletedProcess([], 1, "error")
            with self.assertRaises(SystemExit):
                codex_implement("spec", "rules", None, root, root, implementer="agy")
            with self.assertRaises(SystemExit):
                codex_implement("spec", "rules", None, root, root, implementer="unknown")
