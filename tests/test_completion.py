import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_cycle.core.completion import requirement_inventory, inspect_completion, review_completion, pending_tasks, work_queue, select_target
from ai_cycle.core.verdict import parse_verdict
from ai_cycle.orchestrator import execute_cycle
from ai_cycle.ui.panels import _run_summary


class CompletionTests(unittest.TestCase):
    def test_continuation_requires_explained_source_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            run = root / 'attempt'
            run.mkdir()
            rows = [{'id': i['id'], 'source_status': 'implemented',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in inventory]
            (run / 'checkpoint.json').write_text(json.dumps({'requirements': rows}))
            rows[0]['source_status'] = 'missing'
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            issues, context, validated = inspect_completion(root, run, inventory)
            self.assertIn('Unexplained checkpoint downgrade', issues[0])
            self.assertEqual(validated, [])
            self.assertEqual(context, '')
            rows[0]['reassessment'] = {'previous_status': 'implemented',
                                      'reason': 'Current function returns identity but never assigns the required field.'}
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            issues, context, validated = inspect_completion(root, run, inventory)
            self.assertEqual(validated[0]['source_status'], 'missing')
            self.assertIn('Source model.py:1', context)
            self.assertTrue(issues)
            rows[0]['reassessment']['previous_status'] = 'partial'
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            self.assertEqual(inspect_completion(root, run, inventory)[2], [])

    def test_resume_rejects_old_report_and_uses_incoming_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            previous = root / 'previous'
            attempt = previous / 'attempt-1'
            attempt.mkdir(parents=True)
            rows = [{'id': i['id'], 'source_status': 'implemented' if n == 0 else 'missing',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
                    for n, i in enumerate(inventory)]
            (attempt / 'checkpoint.json').write_text(json.dumps({'requirements': rows}))
            rows[0]['source_status'] = 'missing'
            (attempt / 'completion.json').write_text(json.dumps({'requirements': rows}))
            def implement(*args, **kwargs):
                incoming = json.loads((args[3] / 'checkpoint.json').read_text())['requirements']
                self.assertEqual(incoming[0]['source_status'], 'implemented')
                target = json.loads((args[3] / 'target.json').read_text())
                self.assertEqual(target['id'], inventory[1]['id'])
                self.assertIn('Previous completion report was rejected', args[2])
                raise SystemExit(1)
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.load_previous_feedback', return_value={'run': previous, 'feedback': 'old report'}), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement) as worker:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo', resume=True)
                worker.assert_called_once()

    def test_resume_recovers_target_only_report_and_advances_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            previous = root / 'previous'
            attempt = previous / 'attempt-1'
            attempt.mkdir(parents=True)
            first, second = inventory
            (attempt / 'target.json').write_text(json.dumps({'id': first['id']}))
            (attempt / 'checkpoint.json').write_text(json.dumps({'requirements': []}))
            row = {'id': first['id'], 'source_status': 'implemented',
                   'reason': 'Existing behavior is backed by source.', 'verification_status': 'passed',
                   'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
            (attempt / 'completion.json').write_text(json.dumps({'requirements': [row]}))
            (attempt / 'completion-check.json').write_text(json.dumps({'issues': [
                'Completion report invalid/missing: coverage must contain every active requirement ID exactly once, without extras',
            ]}))
            calls = []

            def implement(*args, **kwargs):
                run = args[3]
                calls.append(run)
                checkpoint = json.loads((run / 'checkpoint.json').read_text())['requirements']
                target = json.loads((run / 'target.json').read_text())
                self.assertEqual(target['id'], second['id'])
                self.assertEqual(checkpoint[0]['source_status'], 'implemented')
                self.assertEqual(checkpoint[1]['source_status'], 'unverified')
                next_row = dict(row, id=second['id'], reason='Second target checked.')
                (run / 'completion.json').write_text(json.dumps({'requirements': [next_row]}))

            verdict = json.dumps({'verdict': 'PASS', 'coverage': [
                {'id': item['id'], 'source_status': 'implemented', 'verification_status': 'pending'}
                for item in inventory
            ]})
            with patch('ai_cycle.orchestrator.require_commands'), \
                    patch('ai_cycle.orchestrator.assert_git_repo'), \
                    patch('ai_cycle.orchestrator.assert_clean_worktree'), \
                    patch('ai_cycle.orchestrator.current_branch', return_value='main'), \
                    patch('ai_cycle.core.openspec.openspec'), \
                    patch('ai_cycle.orchestrator.load_previous_feedback',
                          return_value={'run': previous, 'feedback': 'Old invalid-coverage error'}), \
                    patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), \
                    patch('ai_cycle.orchestrator.get_diff', return_value=''), \
                    patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo', resume=True)
            self.assertEqual(len(calls), 1)
            new_run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(json.loads((new_run / 'attempt-1/target.json').read_text())['id'], second['id'])
            self.assertEqual(json.loads((new_run / 'attempt-1/checkpoint.json').read_text())['requirements'][0]['id'],
                             first['id'])

    def test_resume_accepts_previous_null_target_after_source_is_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            previous = root / 'previous'
            attempt = previous / 'attempt-1'
            attempt.mkdir(parents=True)
            complete = [
                {'id': item['id'], 'source_status': 'implemented',
                 'reason': 'Source evidence verified.', 'verification_status': 'pending',
                 'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
                for item in inventory
            ]
            (attempt / 'target.json').write_text('null')
            (attempt / 'checkpoint.json').write_text(json.dumps({'requirements': complete}))
            (attempt / 'completion.json').write_text(json.dumps({'requirements': complete}))
            (attempt / 'completion-check.json').write_text(json.dumps({'issues': []}))

            def implement(*args, **kwargs):
                run = args[3]
                self.assertIsNone(json.loads((run / 'target.json').read_text()))
                (run / 'completion.json').write_text(json.dumps({'requirements': complete}))

            verdict = json.dumps({'verdict': 'PASS', 'coverage': complete})
            with patch('ai_cycle.orchestrator.require_commands'), \
                    patch('ai_cycle.orchestrator.assert_git_repo'), \
                    patch('ai_cycle.orchestrator.assert_clean_worktree'), \
                    patch('ai_cycle.orchestrator.current_branch', return_value='main'), \
                    patch('ai_cycle.core.openspec.openspec'), \
                    patch('ai_cycle.orchestrator.load_previous_feedback',
                          return_value={'run': previous, 'feedback': 'Resume completed source review'}), \
                    patch('ai_cycle.orchestrator.codex_implement', side_effect=implement) as worker, \
                    patch('ai_cycle.orchestrator.get_diff', return_value=''), \
                    patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo', resume=True)

            worker.assert_called_once()
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertIsNone(json.loads((run / 'attempt-1/target.json').read_text()))

    def fixture(self, root):
        change = root / 'openspec/changes/demo'
        (change / 'specs/identity').mkdir(parents=True)
        (change / 'specs/identity/spec.md').write_text('## ADDED Requirements\n### Requirement: Requester\nUse an employee.\n#### Scenario: Create\n- WHEN create\n- THEN employee\n### Requirement: Department\nFreeze on submit.\n#### Scenario: Submit\n- WHEN submit\n- THEN frozen\n')
        for name in ('proposal.md', 'design.md', 'wireframe.md'):
            (change / name).write_text('# Planning\n')
        (change / 'tasks.md').write_text('# Tasks\n- [ ] 1.1 Implement and test identity\n')
        (change / 'readiness.json').write_text('{"status":"ready","blockers":[]}')
        state = root / '.ai-cycle'
        state.mkdir()
        (state / 'config.json').write_text('{"max_attempts":2}')
        (state / 'RULES.md').write_text('Rules')
        (root / 'model.py').write_text('def identity():\n    return "employee"\n')
        return requirement_inventory(root, 'demo')

    def test_missing_coverage_fake_evidence_and_duplicate_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            run = root / 'run'
            run.mkdir()
            self.assertTrue(inspect_completion(root, run, inventory)[0])
            def report(rows):
                (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
                return inspect_completion(root, run, inventory)
            rows = [{'id': i['id'], 'status': 'implemented', 'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in inventory]
            self.assertFalse(report(rows)[0])
            self.assertTrue(report(rows[:1])[0])
            self.assertTrue(report([rows[0], rows[0]])[0])
            rows[0]['evidence'][0]['path'] = '../outside.py'
            self.assertTrue(report(rows)[0])
            rows[0]['evidence'][0]['path'] = 'missing.py'
            self.assertTrue(report(rows)[0])
            rows[0]['evidence'][0]['path'] = 'model.py'
            rows[0]['evidence'][0]['end_line'] = 999
            self.assertTrue(report(rows)[0])
            rows[0]['evidence'][0]['end_line'] = 2
            rows[0]['status'] = 'deferred'
            self.assertTrue(report(rows)[0])

    def test_target_report_merges_checkpoint_and_preserves_queued_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            run = root / 'attempt'
            run.mkdir()
            first = inventory[0]['id']
            second = inventory[1]['id']
            row = {'id': first, 'source_status': 'implemented', 'reason': 'Verified source behavior.',
                   'verification_status': 'passed',
                   'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
            (run / 'completion.json').write_text(json.dumps({'requirements': [row]}))
            issues, context, checkpoint = inspect_completion(
                root, run, inventory, checkpoint=[], target_id=first,
            )
            self.assertFalse(issues)
            self.assertIn('Source model.py:1', context)
            self.assertEqual([item['source_status'] for item in checkpoint],
                             ['implemented', 'unverified'])
            self.assertEqual(select_target(inventory, checkpoint)['id'], second)

            second_row = dict(row, id=second, reason='Verified next target.')
            (run / 'checkpoint.json').write_text(json.dumps({'requirements': checkpoint}))
            (run / 'completion.json').write_text(json.dumps({'requirements': [second_row]}))
            issues, context, merged = inspect_completion(
                root, run, inventory, checkpoint=checkpoint, target_id=second,
            )
            self.assertFalse(issues)
            self.assertEqual([item['source_status'] for item in merged],
                             ['implemented', 'implemented'])
            self.assertIsNone(select_target(inventory, merged))

            (run / 'completion.json').write_text(json.dumps({'requirements': [row]}))
            issues, _, _ = inspect_completion(
                root, run, inventory, checkpoint=[], target_id=second,
            )
            self.assertIn('must include its assigned requirement', issues[0])

    def test_diff_pass_cannot_hide_missing_department(self):
        with tempfile.TemporaryDirectory() as td:
            inventory = self.fixture(Path(td))
            self.assertTrue(review_completion('VERDICT: PASS', inventory))
            rows = [{'id': i['id'], 'status': 'implemented'} for i in inventory]
            rows[1]['status'] = 'missing'
            self.assertTrue(review_completion(json.dumps({'verdict':'PASS', 'coverage': rows}), inventory))
            rows[1]['status'] = 'implemented'
            self.assertFalse(review_completion(json.dumps({'verdict':'PASS', 'coverage': rows}), inventory))

    def test_source_complete_with_pending_runtime_passes_source_gate_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            run = root / 'attempt'
            run.mkdir()
            rows = [{'id': i['id'], 'source_status': 'implemented', 'verification_status': 'pending',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in inventory]
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            self.assertFalse(inspect_completion(root, run, inventory)[0])
            self.assertFalse(review_completion(json.dumps({'coverage': rows}), inventory))
            rows[0]['status'] = 'missing'
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            self.assertIn('Conflicting status', inspect_completion(root, run, inventory)[0][0])
            self.assertTrue(review_completion(json.dumps({'coverage': rows}), inventory))

    def test_invalid_evidence_downgrades_only_its_requirement(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            run = root / 'attempt'
            run.mkdir()
            rows = [{'id': item['id'], 'source_status': 'implemented', 'verification_status': 'pending',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for item in inventory]
            rows[0]['evidence'][0]['end_line'] = 999
            (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            issues, context, validated = inspect_completion(root, run, inventory)
            self.assertEqual(len(issues), 2)
            self.assertTrue(any('invalid source evidence' in issue for issue in issues))
            self.assertEqual([row['source_status'] for row in validated], ['unverified', 'implemented'])
            self.assertIn('Source model.py:1', context)
            self.assertEqual(context.count('Source model.py:1'), 1)

    def test_queue_and_checkpoint_carry_progress_to_next_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            calls = []
            def implement(*args, **kwargs):
                run = args[3]
                queue = json.loads((run / 'work-items.json').read_text())
                checkpoint = json.loads((run / 'checkpoint.json').read_text())['requirements']
                target = json.loads((run / 'target.json').read_text())
                self.assertEqual(target['id'], inventory[1 if calls else 0]['id'])
                if calls:
                    self.assertEqual(len(queue[0]['pending']), 1)
                    self.assertEqual(len(queue[0]['source_complete']), 1)
                    self.assertEqual(checkpoint[0]['source_status'], 'implemented')
                else:
                    self.assertEqual(len(queue[0]['pending']), 2)
                    self.assertEqual(checkpoint, [])
                calls.append(run)
                rows = [{'id': item['id'], 'source_status': 'implemented' if index == 0 or len(calls) == 2 else 'missing',
                         'verification_status': 'pending', 'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
                        for index, item in enumerate(inventory)]
                (run / 'completion.json').write_text(json.dumps({'requirements': rows}))
            verdict = json.dumps({'verdict': 'PASS', 'coverage': [{'id': i['id'], 'source_status': 'implemented', 'verification_status': 'pending'} for i in inventory]})
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo')
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(json.loads((calls[-1] / 'verification-pending.json').read_text())['requirements']), 2)

    def test_review_pending_verification_prevents_full_pass_even_with_checked_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            (root / 'openspec/changes/demo/tasks.md').write_text('- [x] Complete source\n')
            (root / '.ai-cycle/config.json').write_text('{"validation_commands":["true"]}')
            def implement(*args, **kwargs):
                (args[3] / 'validation.txt').write_text('Mock configured validation passed\n')
                (args[3] / 'completion.json').write_text(json.dumps({'requirements': [
                    {'id': i['id'], 'source_status': 'implemented', 'verification_status': 'passed',
                     'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in inventory]}))
            verdict = json.dumps({'verdict': 'PASS', 'coverage': [{'id': i['id'], 'source_status': 'implemented', 'verification_status': 'pending'} for i in inventory]})
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.run_validation', return_value=True), patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo')
            run = next((root / '.ai-cycle/runs').iterdir())
            result = json.loads((run / 'result.json').read_text())
            self.assertEqual(result['status'], 'awaiting_verification')
            self.assertEqual(len(result['pending_verification']), 2)

    def test_resume_uses_latest_checkpoint_and_all_verified_can_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            (root / 'openspec/changes/demo/tasks.md').write_text('- [x] Complete source and verification\n')
            (root / '.ai-cycle/config.json').write_text('{"validation_commands":["true"]}')
            previous = root / 'previous'
            (previous / 'attempt-2').mkdir(parents=True)
            (previous / 'attempt-10').mkdir()
            complete = [{'id': i['id'], 'source_status': 'implemented', 'verification_status': 'passed',
                         'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]} for i in inventory]
            partial = [dict(row) for row in complete]
            partial[1]['source_status'] = 'missing'
            (previous / 'attempt-2/completion.json').write_text(json.dumps({'requirements': []}))
            (previous / 'attempt-10/completion.json').write_text(json.dumps({'requirements': partial}))
            # Simulate a CLI startup failure: only the incoming checkpoint exists.
            (previous / 'attempt-11').mkdir()
            (previous / 'attempt-11/checkpoint.json').write_text(json.dumps({'requirements': partial}))
            def implement(*args, **kwargs):
                run = args[3]
                self.assertEqual(json.loads((run / 'checkpoint.json').read_text())['requirements'], partial)
                queue = json.loads((run / 'work-items.json').read_text())
                self.assertEqual(queue[0]['pending'], [inventory[1]['id']])
                (run / 'completion.json').write_text(json.dumps({'requirements': complete}))
            verdict = json.dumps({'verdict': 'PASS', 'coverage': complete})
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.load_previous_feedback', return_value={'run': previous, 'feedback': 'Finish department'}), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo', resume=True)
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(json.loads((run / 'result.json').read_text())['status'], 'passed')

    def test_missing_report_retries_the_same_unfinished_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement') as implement, patch('ai_cycle.orchestrator.claude_review') as reviewer:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo', max_attempts=2)
                self.assertEqual(implement.call_count, 2)
                targets = [json.loads((call.args[3] / 'target.json').read_text())['id'] for call in implement.call_args_list]
                self.assertEqual(targets[0], targets[1])
                reviewer.assert_not_called()
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(json.loads((run / 'result.json').read_text())['status'], 'partial')
            self.assertIn('PARTIAL', _run_summary(run)['result'])
            self.assertTrue((run / 'terminal-feedback.txt').exists())
            self.assertIn('REQUIRED TARGET INCOMPLETE', (run / 'terminal-feedback.txt').read_text())

    def test_target_only_report_is_progress_not_invalid_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)

            def implement(*args, **kwargs):
                run = args[3]
                target = json.loads((run / 'target.json').read_text())
                row = {'id': target['id'], 'source_status': 'implemented',
                       'reason': 'The target is already implemented in source.',
                       'verification_status': 'passed',
                       'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
                (run / 'completion.json').write_text(json.dumps({'requirements': [row]}))

            with patch('ai_cycle.orchestrator.require_commands'), \
                    patch('ai_cycle.orchestrator.assert_git_repo'), \
                    patch('ai_cycle.orchestrator.assert_clean_worktree'), \
                    patch('ai_cycle.orchestrator.current_branch', return_value='main'), \
                    patch('ai_cycle.core.openspec.openspec'), \
                    patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), \
                    patch('ai_cycle.orchestrator.claude_review') as reviewer:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo', max_attempts=1)
                reviewer.assert_not_called()

            run = next((root / '.ai-cycle/runs').iterdir())
            attempt = run / 'attempt-1'
            issues = json.loads((attempt / 'completion-check.json').read_text())['issues']
            self.assertTrue(any('Package source progress: 1/2 implemented' in issue for issue in issues))
            self.assertFalse(any('coverage must contain every active requirement ID' in issue
                                 for issue in issues))
            self.assertFalse((attempt / 'target-result.json').exists())

    def test_partial_target_retries_up_to_attempt_limit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            calls = []
            def implement(*args, **kwargs):
                calls.append(args[3])
                rows = [{'id': item['id'], 'status': 'partial', 'reason': f'Attempt {len(calls)}'} for item in inventory]
                (args[3] / 'completion.json').write_text(json.dumps({'requirements': rows}))
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.claude_review') as reviewer:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo', max_attempts=2)
                self.assertEqual(len(calls), 2)
                self.assertEqual([json.loads((call / 'target.json').read_text())['id'] for call in calls],
                                 [inventory[0]['id'], inventory[0]['id']])
                reviewer.assert_not_called()

    def test_unrelated_completed_requirement_does_not_satisfy_required_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            def implement(*args, **kwargs):
                rows = [{'id': i['id'], 'source_status': 'missing' if index == 0 else 'implemented',
                         'reason': 'Manager mapping requires a decision' if index == 0 else 'Other source completed',
                         'resolution_options': [{'label': 'Explicit manager configuration', 'tradeoff': 'Requires maintained warehouse configuration'}],
                         'evidence': [{'path': 'model.py', 'line': 1, 'end_line': 2}]}
                        for index, i in enumerate(inventory)]
                (args[3] / 'completion.json').write_text(json.dumps({'requirements': rows}))
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement) as worker, patch('ai_cycle.orchestrator.claude_review') as reviewer:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo', max_attempts=2)
                self.assertEqual(worker.call_count, 2)
                reviewer.assert_not_called()
            run = next((root / '.ai-cycle/runs').iterdir())
            target = json.loads((run / 'attempt-2/target-result.json').read_text())
            self.assertEqual(target['id'], inventory[0]['id'])
            self.assertEqual(target['source_status'], 'missing')
            self.assertEqual(len(target['resolution_options']), 1)

    def test_target_prioritizes_missing_over_partial_and_skips_complete(self):
        inventory = [{'id': str(i), 'path': 'spec.md'} for i in range(3)]
        rows = [{'id': '0', 'status': 'implemented', 'evidence': [{}]},
                {'id': '1', 'status': 'partial'}, {'id': '2', 'status': 'missing'}]
        self.assertEqual(select_target(inventory, rows)['id'], '2')
        rows[2] = {'id': '2', 'source_status': 'implemented', 'evidence': [{}]}
        self.assertEqual(select_target(inventory, rows)['id'], '1')
        rows[1] = {'id': '1', 'source_status': 'implemented', 'evidence': [{}]}
        self.assertIsNone(select_target(inventory, rows))

    def test_history_and_verdict_do_not_infer_pass(self):
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            (run / 'attempt-1').mkdir()
            self.assertNotIn('PASS', _run_summary(run)['result'])
        self.assertEqual(parse_verdict('Tests PASS, but review was interrupted'), 'UNKNOWN')
        self.assertEqual(parse_verdict('{"verdict":"PASS","blockers":["department missing"]}'), 'CHANGES_REQUIRED')
        self.assertEqual(parse_verdict('{"verdict":"PASS","spec_questions":["currency?"]}'), 'NEEDS_HUMAN')

    def test_implementer_exit_failure_preserves_resume_feedback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=SystemExit(1)), patch('ai_cycle.orchestrator.claude_review') as reviewer:
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo')
                reviewer.assert_not_called()
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(json.loads((run / 'result.json').read_text())['status'], 'failed')
            self.assertIn('IMPLEMENTER INTERRUPTED', (run / 'terminal-feedback.txt').read_text())

    def test_pending_task_markers_and_evidence_are_not_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'tasks.md'
            path.write_text('- [x] done\n- [ X ] done too\n- [ ] pending\n- [~] partial\n- [] pending empty\n## Implementation Evidence\n- [ ] old note\n')
            self.assertEqual(pending_tasks(path), ['pending', 'partial', 'pending empty'])

    def test_independent_gap_overrides_pass_and_feeds_next_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            def implement(*args, **kwargs):
                report = {'requirements': [{'id': i['id'], 'status': 'implemented', 'evidence':[{'path':'model.py','line':1,'end_line':2}]} for i in inventory]}
                (args[3] / 'completion.json').write_text(json.dumps(report))
            coverage = [{'id': i['id'], 'status': 'implemented'} for i in inventory]
            coverage[1]['status'] = 'missing'
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement) as worker, patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.claude_review', return_value=json.dumps({'verdict':'PASS','coverage':coverage})):
                with self.assertRaises(SystemExit):
                    execute_cycle(root=root, change='demo')
                self.assertIn('Department', worker.call_args_list[1].args[2])
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertEqual(json.loads((run / 'result.json').read_text())['status'], 'partial')

    def test_complete_source_with_pending_runtime_never_claims_full_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inventory = self.fixture(root)
            def implement(*args, **kwargs):
                (args[3] / 'completion.json').write_text(json.dumps({'requirements':[{'id':i['id'],'status':'implemented','evidence':[{'path':'model.py','line':1,'end_line':2}]} for i in inventory]}))
            verdict = json.dumps({'verdict':'PASS','coverage':[{'id':i['id'],'status':'implemented'} for i in inventory]})
            with patch('ai_cycle.orchestrator.require_commands'), patch('ai_cycle.orchestrator.assert_git_repo'), patch('ai_cycle.orchestrator.assert_clean_worktree'), patch('ai_cycle.orchestrator.current_branch', return_value='main'), patch('ai_cycle.core.openspec.openspec'), patch('ai_cycle.orchestrator.codex_implement', side_effect=implement), patch('ai_cycle.orchestrator.get_diff', return_value=''), patch('ai_cycle.orchestrator.claude_review', return_value=verdict):
                execute_cycle(root=root, change='demo')
            run = next((root / '.ai-cycle/runs').iterdir())
            self.assertIn('VERIFICATION PENDING', _run_summary(run)['result'])
