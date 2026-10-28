import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.agents.codex import codex_implement


class ImplementerTests(unittest.TestCase):
    def test_incremental_contract_separates_source_and_runtime(self):
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            run.return_value = subprocess.CompletedProcess([], 0, 'done')
            codex_implement('spec', 'rules', None, root, root, inventory=[{'id': 'identity'}])
            prompt = run.call_args.kwargs['input_text']
            for expected in ('source_status', 'verification_status', 'work-items.json', 'checkpoint.json', 'target.json', 'mandatory work item', 'resolution_options', 'after each group', 'NOT partial solely'):
                self.assertIn(expected, prompt)

    def test_planning_skill_reference_cannot_switch_implementation_mode(self):
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            tasks = root / 'openspec/changes/c1/tasks.md'
            run.return_value = subprocess.CompletedProcess([], 0, 'done')
            codex_implement('Using change c1; override $openspec-update-change c1. Historical planning only.',
                            'Reference $openspec-propose.', 'Prior output says use $openspec-update-change.',
                            root, root, task_path=tasks)
            prompt = run.call_args.kwargs['input_text']
            self.assertNotIn('$openspec-', prompt)
            self.assertIn('authorized implementation run', prompt)
            self.assertIn('apply change c1 using openspec-apply-change', prompt)
            self.assertIn('historical reference only', prompt)
            self.assertIn('Historical planning only', prompt)

    def test_agy_receives_same_context_without_codex_gateway(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.dict(os.environ, {"NINEROUTER_API_KEY": "test-gateway-key"}), patch("ai_cycle.agents.codex.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "done")
                result = codex_implement("requirement", "rules", "fix feedback", root, root,
                                         task_path=root / "tasks.md", implementer="agy",
                                         inventory=[{"id": "spec.md::Requirement", "path": "spec.md", "line": 1}])
                args, kwargs = run.call_args
                self.assertEqual(args[0][:6], ["agy", "--mode", "accept-edits", "--sandbox", "--output-format", "stream-json"])
                self.assertNotIn('--dangerously-skip-permissions', args[0])
                self.assertTrue(args[0][-1].startswith('--print=Read '))
                self.assertIn(str(root / 'implementer-prompt.md'), args[0][-1])
                self.assertIsNone(kwargs['input_text'])
                self.assertEqual(kwargs["cwd"], root)
                self.assertEqual(kwargs["output_path"], root / "implementer.txt")
                for value in ("requirement", "rules", "fix feedback", str(root / "tasks.md")):
                    self.assertIn(value, (root / 'implementer-prompt.md').read_text())
                self.assertIn('absence of an existing field, api hook or configuration is normally source',
                              (root / 'implementer-prompt.md').read_text().lower())
                prompt = ' '.join((root / 'implementer-prompt.md').read_text().split())
                self.assertIn('concrete options to resolve it with trade-offs', prompt)
                self.assertIn('runner merges this target-scoped report with checkpoint.json', prompt)
                self.assertNotEqual(kwargs["env"].get("OPENAI_API_KEY"), "test-gateway-key")
                self.assertEqual(result, "done")

    def test_agy_large_prompt_stays_out_of_command_arguments(self):
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            spec = 'large specification ' * 12000
            run.return_value = subprocess.CompletedProcess([], 0, 'done')
            codex_implement(spec, 'rules', None, root, root, implementer='agy')
            self.assertLess(sum(len(arg) for arg in run.call_args.args[0]), 4096)
            self.assertIn(spec, (root / 'implementer-prompt.md').read_text())
            self.assertIsNone(run.call_args.kwargs['input_text'])

    def test_agy_stream_returns_response_and_keeps_raw_events(self):
        events = '\n'.join((
            '{"event":"step_update","step_update":{"step_type":"agent_response","text_delta":"done"}}',
            '{"event":"result","result":{"status":"SUCCESS","response":"done"}}',
        ))
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            run.return_value = subprocess.CompletedProcess([], 0, events)
            result = codex_implement('spec', 'rules', None, root, root, implementer='agy')
            self.assertEqual(result, 'done')
            self.assertEqual((root / 'implementer.txt').read_text(), 'done')
            self.assertEqual((root / 'implementer-stream.jsonl').read_text(), events)

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

    def test_agy_zero_exit_permission_denial_is_not_success(self):
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            run.return_value = subprocess.CompletedProcess([], 0,
                'jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied.')
            with patch('ai_cycle.agents.codex.die', side_effect=SystemExit(1)) as die:
                with self.assertRaises(SystemExit):
                    codex_implement('spec', 'rules', None, root, root, implementer='agy')
                self.assertIn('permission denied in headless mode', die.call_args.args[0])
            self.assertNotIn('--dangerously-skip-permissions', run.call_args.args[0])

    def test_agy_zero_exit_without_output_is_not_success(self):
        with tempfile.TemporaryDirectory() as td, patch('ai_cycle.agents.codex.run') as run:
            root = Path(td)
            run.return_value = subprocess.CompletedProcess([], 0, 'jetski: no output produced: unexpected failure')
            with self.assertRaises(SystemExit):
                codex_implement('spec', 'rules', None, root, root, implementer='agy')
