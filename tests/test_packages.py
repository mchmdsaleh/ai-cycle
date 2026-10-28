import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.core.completion import requirement_inventory
from ai_cycle.core.packages import MAX_PACKAGE_CONTEXT_BYTES, package_context
from ai_cycle.orchestrator import execute_cycle
from ai_cycle.resume import load_previous_feedback, sha256_text
from ai_cycle.ui.panels import _run_summary
from test_openspec import payload


class PackageTests(unittest.TestCase):
    def fixture(self, root):
        change = root / 'openspec/changes/demo'
        for name, content in payload()['files'].items():
            path = change / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        other = change / 'specs/other/spec.md'
        other.parent.mkdir()
        other.write_text('## ADDED Requirements\n### Requirement: Unrelated\nUNRELATED_REQUIREMENT_SENTINEL\n#### Scenario: Other\n- WHEN other\n- THEN other\n')
        (root / '.ai-cycle').mkdir()
        (root / '.ai-cycle/RULES.md').write_text('Preserve safety')
        (root / '.ai-cycle/config.json').write_text(json.dumps({
            'validation_commands': ['global check'],
            'package_validation_commands': {'payment-export': ['package check']},
        }))
        (root / 'model.py').write_text('def export():\n    return "csv"\n')
        return requirement_inventory(root, 'demo')

    def test_package_context_keeps_shared_constraints_without_other_specs_or_task_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            tasks = root / 'openspec/changes/demo/tasks.md'
            tasks.write_text(tasks.read_text() + '\n## Implementation evidence\nOLD_AUDIT_SENTINEL\n')
            context, selected = package_context(root, 'demo', 'payment-export', inventory)
            self.assertEqual(len(selected), 1)
            self.assertIn('Export payments', context)
            self.assertIn('Existing payment model', context)
            self.assertNotIn('UNRELATED_REQUIREMENT_SENTINEL', context)
            self.assertNotIn('OLD_AUDIT_SENTINEL', context)
            self.assertLess(len(context.encode()), MAX_PACKAGE_CONTEXT_BYTES)
            for name in ('../other', 'missing', '/tmp/other'):
                with self.assertRaises(SystemExit):
                    package_context(root, 'demo', name, inventory)

    def test_oversized_context_fails_instead_of_silently_dropping_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            (root / 'openspec/changes/demo/design.md').write_text('x' * MAX_PACKAGE_CONTEXT_BYTES)
            with self.assertRaises(SystemExit):
                package_context(root, 'demo', 'payment-export', inventory)

    def test_package_review_is_not_full_change_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            selected = [i for i in inventory if i['path'] == 'specs/payment-export/spec.md']
            rows = [{'id': i['id'], 'source_status': 'implemented', 'verification_status': 'pending',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in selected]
            def implement(spec, rules, feedback, run_dir, cwd, **kwargs):
                self.assertNotIn('UNRELATED_REQUIREMENT_SENTINEL', spec)
                self.assertEqual(kwargs['inventory'], selected)
                (run_dir / 'completion.json').write_text(json.dumps({'requirements': rows}))
            def validate(commands, run_dir, cwd, progress):
                self.assertEqual(commands, ['package check'])
                (run_dir / 'validation.txt').write_text('package check: passed')
                return True
            def review(spec, rules, diff, run_dir, **kwargs):
                self.assertNotIn('UNRELATED_REQUIREMENT_SENTINEL', spec)
                self.assertIn('package check: passed', spec)
                return json.dumps({'verdict': 'PASS', 'coverage': rows})
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.run_validation', side_effect=validate), patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.claude_review', side_effect=review):
                execute_cycle(root=root, change='demo', package='payment-export')
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(len(json.loads((run / 'global-requirements.json').read_text())), 2)
            self.assertEqual(len(json.loads((run / 'requirements.json').read_text())), 1)
            result = json.loads((run / 'result.json').read_text())
            self.assertEqual(result['status'], 'package_reviewed')
            self.assertTrue(result['integration_required'])
            self.assertFalse(result['verification_complete'])
            checkpoint = json.loads((run / 'attempt-1/package-checkpoint.json').read_text())
            self.assertEqual(checkpoint['evidence_sha256']['model.py'], sha256_text((root / 'model.py').read_text()))
            self.assertNotIn('PASS', _run_summary(run)['result'])

    def test_resume_never_crosses_package_scope(self):
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td)
            previous = runs / 'previous'
            previous.mkdir()
            (previous / 'metadata.json').write_text(json.dumps({'branch': 'main', 'spec_hash': sha256_text('spec'), 'package': 'payment-export'}))
            (previous / 'terminal-feedback.txt').write_text('Finish package')
            for name in (None, 'other'):
                self.assertIsNone(load_previous_feedback(runs, runs / 'current', 'spec', 'main', package=name))
            self.assertEqual(load_previous_feedback(runs, runs / 'current', 'spec', 'main', package='payment-export')['run'], previous)

    def test_package_requires_openspec_change(self):
        with self.assertRaises(SystemExit), patch('ai_cycle.orchestrator.codex_implement') as implement:
            execute_cycle(package='payment-export')
        implement.assert_not_called()
