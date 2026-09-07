import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_rpa_collab import MODULE as c, SCRIPT_DIR, bootstrap_args, gate_args, write_workspace, write_task


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rf3-中文-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_workspace(self.root)
        (self.root / 'AGENTS.md').write_text('test evidence', encoding='utf-8')
        c.bootstrap_collaboration(bootstrap_args(self.root))
        self.project = self.root / '.project-gates/project.json'
        data = c.read_json(self.project)
        data['current_gate'] = 'G2'
        c.write_json_atomic(self.project, data)
        write_task(self.root, meta={'delivery_route': {'change_class': 'test', 'entry': 'G2',
                   'required_reviews': ['G2', 'G3'], 'completed_reviews': [], 'project_revalidations': []}})
        self.task = self.root / '.trellis/tasks/demo-delivery/task.json'
        self.history = self.root / '.project-gates/gate-history.md'
        self.args = gate_args(self.root, accepted_gate='G2', event_id='rf3-unique')

    def recover(self, **kwargs):
        return c.recover_operation(argparse.Namespace(project_root=str(self.root),
            dry_run=kwargs.get('dry_run', False), confirm_recovery=kwargs.get('confirm', True)))

    def fail_at(self, filename):
        original = c.transaction.atomic_text
        def fail(path, text):
            if path.name == filename:
                raise OSError('injected disk failure')
            return original(path, text)
        with mock.patch.object(c.transaction, 'atomic_text', side_effect=fail):
            return c.close_gate(self.args)

    def assert_finished(self):
        self.assertEqual(c.read_json(self.project)['current_gate'], 'G3')
        self.assertEqual(c.read_json(self.task)['meta']['delivery_route']['completed_reviews'], ['G2'])
        self.assertEqual(self.history.read_text(encoding='utf-8').count('- event_id: rf3-unique'), 1)
        self.assertIsNone(c.transaction.inspect(self.root))

    def test_recovery_at_every_write_boundary(self):
        before = {p: p.read_bytes() for p in (self.history, self.project, self.task)}
        for filename in ('gate-history.md', 'project.json', 'task.json'):
            with self.subTest(filename=filename):
                for p, content in before.items():
                    p.write_bytes(content)
                self.assertFalse(self.fail_at(filename)['ok'])
                self.assertFalse(c.build_status(self.root)['ok'])
                self.assertEqual(c.suggest_action(c.build_status(self.root))['recommended_action'], 'operation_recover')
                with self.assertRaises(c.transaction.TransactionError):
                    c.close_gate(self.args)
                self.assertEqual(self.recover()['status'], 'recovered')
                self.assert_finished()
                self.assertEqual(self.recover()['status'], 'nothing_pending')

    def test_journal_write_failure_changes_no_authority(self):
        before = [p.read_bytes() for p in (self.history, self.project, self.task)]
        with self.assertRaises(OSError):
            self.fail_at('pending-operation.json')
        self.assertEqual(before, [p.read_bytes() for p in (self.history, self.project, self.task)])

    def test_revalidation_interruption_and_duplicate_event_rejected(self):
        data = c.read_json(self.project)
        data.update(current_gate='G5', status='operational')
        c.write_json_atomic(self.project, data)
        original = c.write_json_atomic
        def fail(path, data):
            if path.name == 'project.json':
                raise OSError('snapshot interrupted')
            original(path, data)
        with mock.patch.object(c, 'write_json_atomic', side_effect=fail):
            self.assertFalse(c.revalidate_gate(self.args)['ok'])
        self.recover()
        self.assertEqual(c.read_json(self.project)['current_gate'], 'G5')
        self.assertEqual(c.read_json(self.task)['meta']['delivery_route']['completed_reviews'], ['G2'])
        before = self.history.read_bytes()
        with self.assertRaises(c.CollabError):
            c.revalidate_gate(self.args)
        self.assertEqual(before, self.history.read_bytes())

    def test_amendment_interruption_preserves_old_event_and_new_baseline(self):
        c.close_gate(self.args)
        self.args.event_id = 'rf3-amendment'
        self.args.baseline_commit = 'a' * 40
        original = c.write_json_atomic
        def fail(path, data):
            if path.name == 'project.json':
                raise OSError('snapshot interrupted')
            original(path, data)
        with mock.patch.object(c, 'resolve_git_commit', return_value='a' * 40), \
             mock.patch.object(c, 'write_json_atomic', side_effect=fail):
            self.assertFalse(c.amend_gate(self.args)['ok'])
        self.recover()
        self.assertEqual(c.read_json(self.project)['accepted_baseline']['commit'], 'a' * 40)
        history = self.history.read_text(encoding='utf-8')
        self.assertEqual(history.count('- event_id: rf3-unique'), 1)
        self.assertEqual(history.count('- event_id: rf3-amendment'), 1)
        self.assertEqual(c.read_json(self.project)['current_gate'], 'G3')

    def test_recovery_can_be_interrupted_again(self):
        self.fail_at('project.json')
        original = c.write_json_atomic
        def fail(path, data):
            if path.name == 'task.json':
                raise OSError('second interruption')
            original(path, data)
        with mock.patch.object(c, 'write_json_atomic', side_effect=fail):
            with self.assertRaises(c.transaction.TransactionError):
                self.recover()
        self.recover()
        self.assert_finished()

    def test_conflict_blocks_all_remaining_writes(self):
        self.fail_at('gate-history.md')
        self.task.write_text('{"user": "changed"}', encoding='utf-8')
        before = [p.read_bytes() for p in (self.history, self.project, self.task)]
        with self.assertRaises(c.transaction.TransactionError):
            self.recover()
        self.assertEqual(before, [p.read_bytes() for p in (self.history, self.project, self.task)])
        self.assertIsNotNone(c.transaction.inspect(self.root))

    def test_recovery_dry_run_and_explicit_authorization(self):
        self.fail_at('project.json')
        before = [p.read_bytes() for p in (self.history, self.project, self.task)]
        self.assertEqual(self.recover(dry_run=True, confirm=False)['status'], 'recoverable')
        with self.assertRaises(c.CollabError):
            self.recover(confirm=False)
        self.assertEqual(before, [p.read_bytes() for p in (self.history, self.project, self.task)])

    def test_corrupt_journal_fails_closed(self):
        self.fail_at('project.json')
        c.transaction.pending_path(self.root).write_text('{bad', encoding='utf-8')
        self.assertEqual(c.build_status(self.root)['pending_operation']['state'], 'invalid')
        with self.assertRaises(c.transaction.TransactionError):
            self.recover()

    def test_recovery_rejects_outside_path_even_with_valid_checksum(self):
        self.fail_at('project.json')
        path = c.transaction.pending_path(self.root)
        data = json.loads(path.read_text(encoding='utf-8'))
        data.pop('sha256')
        data['writes'][0]['path'] = '../outside.md'
        data['sha256'] = c.transaction.digest(data)
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(c.transaction.TransactionError):
            self.recover()

    def test_event_id_matching_is_exact(self):
        self.assertFalse(c.history_has_event('- event_id: accepted-long\n', 'accepted'))
        self.assertTrue(c.history_has_event('- event_id: accepted\n', 'accepted'))

    def test_noop_recovery_after_journal_cleanup_failure(self):
        original = Path.unlink
        def fail(path, *args, **kwargs):
            if path.name == 'pending-operation.json':
                raise OSError('cleanup interrupted')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'unlink', fail):
            self.assertFalse(c.close_gate(self.args)['ok'])
        with mock.patch.object(c, 'write_json_atomic', side_effect=AssertionError('must not rewrite')):
            self.recover()
        self.assert_finished()

    def test_dry_run_leaves_no_journal_or_writes(self):
        self.args.dry_run = True
        before = [p.read_bytes() for p in (self.history, self.project, self.task)]
        self.assertTrue(c.close_gate(self.args)['ok'])
        self.assertIsNone(c.transaction.inspect(self.root))
        self.assertEqual(before, [p.read_bytes() for p in (self.history, self.project, self.task)])

    def test_archive_and_route_changes_blocked_while_pending(self):
        self.fail_at('task.json')
        for function in (c.archive_check, c.set_delivery_route, c.bootstrap_collaboration):
            with self.assertRaises(c.transaction.TransactionError):
                function(self.args)

    def test_second_process_cannot_write_under_lock(self):
        command = [sys.executable, str(SCRIPT_DIR / 'rpa_collab.py'), '--project-root', str(self.root),
                   '--task', 'demo-delivery', 'gate-close', '--accepted-gate', 'G2',
                   '--confirm-user-acceptance', '--evidence', 'AGENTS.md']
        with c.transaction.project_lock(self.root):
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Another Gate writer', result.stdout)
        self.assertEqual(c.read_json(self.project)['current_gate'], 'G2')

    def test_process_death_and_fresh_cli_recovery(self):
        code = """import sys, os
sys.path.insert(0, sys.argv[1])
import project_gate_controller as c
import rpa_collab
original = c.write_json_atomic
def die(path, data):
    if path.name == 'project.json': os._exit(91)
    original(path, data)
c.write_json_atomic = die
rpa_collab.main(sys.argv[2:])
"""
        result = subprocess.run([sys.executable, '-c', code, str(SCRIPT_DIR), '--project-root', str(self.root),
             '--task', 'demo-delivery', 'gate-close', '--accepted-gate', 'G2', '--event-id', 'rf3-unique',
             '--confirm-user-acceptance', '--evidence', 'AGENTS.md'], capture_output=True)
        self.assertEqual(result.returncode, 91)
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / 'rpa_collab.py'), '--project-root', str(self.root),
             'operation-recover', '--confirm-recovery'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_finished()


if __name__ == '__main__':
    unittest.main()
