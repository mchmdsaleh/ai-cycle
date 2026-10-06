import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from rich.live import Live

from ai_cycle.core.git import get_diff
from ai_cycle.core.runner import run
from ai_cycle.agents.claude import claude_review
from ai_cycle.orchestrator import build_feedback, execute_cycle
from ai_cycle.ui.progress import CycleProgress


class ProgressTests(unittest.TestCase):
    def test_claude_review_is_one_shot_and_has_timeout(self):
        with tempfile.TemporaryDirectory() as td, patch("ai_cycle.agents.claude.run") as run_claude:
            run_claude.return_value = subprocess.CompletedProcess([], 0, "VERDICT: PASS")
            result = claude_review("spec", "rules", "diff", Path(td), model="fast-model")
            args, kwargs = run_claude.call_args
            self.assertEqual(args[0][0:3], ["claude", "--model", "fast-model"])
            self.assertIn("--safe-mode", args[0])
            self.assertEqual(args[0][args[0].index("--tools") + 1], "")
            self.assertEqual(kwargs["timeout"], 120)
            self.assertIn("SPEC:\nspec", kwargs["input_text"])
            self.assertEqual(result, "VERDICT: PASS")

    def test_live_clock_and_literal_log(self):
        console = Console(file=io.StringIO(), force_terminal=True, width=100)
        progress = CycleProgress(console)
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "output.txt"
            log.write_text("[red]literal output[/red]\n")
            with patch("ai_cycle.ui.progress.time.monotonic", return_value=10):
                progress.start_stage("Review", log)
            with Live(console=console, get_renderable=progress.render, auto_refresh=False) as live:
                for now, elapsed in ((11, "1s"), (14, "4s")):
                    with patch("ai_cycle.ui.progress.time.monotonic", return_value=now):
                        table = live.get_renderable()
                    self.assertEqual(table.columns[2]._cells[0], elapsed)
                    self.assertIn("[red]literal output[/red]", table.caption.plain)
            progress.complete_stage("Review", success=False)
            self.assertEqual(progress.stages["Review"], "failed")

    def test_log_written_before_exit_and_preserved_on_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "agent.txt"
            # The child verifies its output is already on disk before it exits.
            code = "import pathlib,sys; print(input(), flush=True); assert 'hello' in pathlib.Path(sys.argv[1]).read_text(); print('stderr', file=sys.stderr)"
            result = run([sys.executable, "-c", code, str(log)], input_text="hello\n", output_path=log, quiet=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, log.read_text())
            self.assertIn("stderr", result.stdout)
            with self.assertRaises(subprocess.TimeoutExpired):
                run([sys.executable, "-u", "-c", "import time; print('partial'); time.sleep(10)"], output_path=log, timeout=0.5, quiet=True)
            self.assertIn("partial", log.read_text())

    def test_diff_excludes_tracked_and_untracked_cycle_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            git("init", "-b", "main")
            (root / "app.txt").write_text("before\n")
            (root / ".ai-cycle").mkdir()
            (root / ".ai-cycle/config.json").write_text("{}")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "base")
            git("switch", "-c", "feature")
            (root / "committed.txt").write_text("feature history\n")
            git("add", "committed.txt")
            git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "feature history")
            (root / "app.txt").write_text("after\n")
            (root / "new.txt").write_text("new code\n")
            (root / ".ai-cycle/config.json").write_text('{"changed": true}')
            (root / ".ai-cycle/agent.log").write_text("large agent output\n")
            diff = get_diff(root)
            self.assertIn("+after", diff)
            self.assertIn("+new code", diff)
            self.assertNotIn("feature history", diff)
            self.assertNotIn(".ai-cycle", diff)
            self.assertIn("feature history", get_diff(root, "main"))

    def test_validation_failure_skips_review_and_default_postmortem(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / ".ai-cycle"
            state.mkdir()
            (state / "config.json").write_text('{"validation_commands": ["exit 1"]}')
            (state / "spec.md").write_text("Task")
            (state / "RULES.md").write_text("Rules")
            with patch("ai_cycle.orchestrator.require_commands"), patch("ai_cycle.orchestrator.assert_git_repo"), patch("ai_cycle.orchestrator.assert_clean_worktree"), patch("ai_cycle.orchestrator.current_branch", return_value="main"), patch("ai_cycle.orchestrator.codex_implement"), patch("ai_cycle.orchestrator.get_diff", return_value="diff"), patch("ai_cycle.orchestrator.claude_review") as review, patch("ai_cycle.orchestrator.propose_rule") as postmortem:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, max_attempts=1)
                review.assert_not_called()
                postmortem.assert_not_called()
            self.assertNotIn("CLAUDE CODE REVIEW", build_feedback("", "failed"))


if __name__ == "__main__":
    unittest.main()
