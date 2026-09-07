import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from test_rpa_collab import MODULE as c, SCRIPT_DIR, bootstrap_args, gate_args, write_workspace, write_task, write_evidence_summary
import delivery_guard as guard
from github_delivery import EvidenceError, GitHub, github_url


class Provider:
    def __init__(self, commit):
        self.pr = {'url': 'https://github.com/example/project/pull/2', 'head': commit,
                   'merge': None, 'merged': False, 'state': 'open', 'draft': False,
                   'created_at': '2026-09-07T00:00:00Z', 'author': 'implementer', 'reviews': []}
        self.runs = []
    def issue(self, url):
        return {'url': url, 'state': 'open'}
    def pull(self, url):
        return copy.deepcopy(self.pr)
    def checks(self, repo, commit):
        return self.runs


class DeliveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rf4-中文-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        write_workspace(self.root)
        (self.root / 'AGENTS.md').write_text('fixture', encoding='utf-8')
        c.bootstrap_collaboration(bootstrap_args(self.root))
        self.git('init')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('remote', 'add', 'origin', 'https://github.com/example/project.git')
        self.git('add', 'AGENTS.md', '.trellis/config.yaml')
        self.git('commit', '-m', 'fixture')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.provider = Provider(self.commit)
        self.task_path = self.root / '.trellis/tasks/demo-delivery/task.json'
        self.contract = {'schema_version': 1, 'confirmed': True, 'scope': 'selected delivery',
                         'issue_url': 'https://github.com/example/project/issues/1',
                         'review_source': 'recorded_review', 'check_source': 'local_checks',
                         'required_checks': ['unit-tests']}
        self.meta = {'delivery_contract': self.contract,
                     'delivery_requirements': {'require_pr': True, 'require_runner': False, 'require_user_acceptance': True},
                     'archive_evidence': {'commit': self.commit, 'pr_url': self.provider.pr['url'],
                        'review_ref': self.make_record('review'), 'check_refs': {'unit-tests': self.make_record('local_check')},
                        'acceptance_ref': self.make_record('user_acceptance'),
                        'acceptance_criteria': [{'result': 'passed', 'evidence_refs': ['AGENTS.md']}],
                        'technical_checks': [{'result': 'passed', 'evidence_refs': ['AGENTS.md']}],
                        'final_summary': 'fixture accepted'}}
        self.save()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8').stdout

    def make_record(self, kind):
        folder = self.root / '.trellis/tasks/demo-delivery/evidence'
        folder.mkdir(parents=True, exist_ok=True)
        artifact = folder / (kind + '.md')
        artifact.write_text('Independent fixture output / review narrative', encoding='utf-8')
        value = {'schema_version': 1, 'kind': kind, 'result': 'passed', 'actor': 'test-user',
                 'actor_kind': 'human', 'statement': 'fixture statement', 'task_id': 'demo-delivery',
                 'commit': self.commit, 'scope': 'selected delivery', 'issue_url': self.contract['issue_url'],
                 'artifact': {'path': artifact.relative_to(self.root).as_posix(),
                              'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}}
        if kind == 'local_check':
            value.update(name='unit-tests', command=['python', '-m', 'pytest'], exit_code=0)
        path = folder / (kind + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        return path.relative_to(self.root).as_posix()

    def save(self):
        write_task(self.root, meta=self.meta)

    def check(self, stage='G3', **kwargs):
        return guard.check(c, self.root, 'demo-delivery', stage, provider=self.provider, **kwargs)

    def test_local_evidence_is_not_called_ci(self):
        result = self.check()
        self.assertTrue(result['ready'], result)
        self.assertEqual(result['facts']['checks'][0]['evidence_kind'], 'local_check')
        self.assertEqual(result['facts']['review']['kind'], 'local_record')

    def test_plain_url_and_legacy_records_never_grant_readiness(self):
        del self.meta['delivery_contract']; self.save()
        self.assertFalse(self.check()['ready'])
        result = c.archive_check(argparse.Namespace(project_root=str(self.root), task='demo-delivery', user_accepted=True))
        self.assertFalse(result['ready'])

    def test_changed_scope_commit_task_or_artifact_is_rejected(self):
        path = self.root / self.meta['archive_evidence']['review_ref']
        original = path.read_text(encoding='utf-8')
        for key in ('scope', 'task_id', 'commit', 'issue_url'):
            with self.subTest(key=key):
                value = json.loads(original); value[key] = 'different'
                path.write_text(json.dumps(value), encoding='utf-8')
                self.assertFalse(self.check()['ready'])
        path.write_text(original, encoding='utf-8')
        artifact = self.root / json.loads(original)['artifact']['path']
        artifact.write_text('changed', encoding='utf-8')
        self.assertFalse(self.check()['ready'])

    def test_uncommitted_business_change_blocks(self):
        (self.root / 'AGENTS.md').write_text('changed', encoding='utf-8')
        self.assertIn('delivery_version', self.check()['missing'])

    def test_record_only_commit_preserves_delivery(self):
        self.git('add', '.trellis/tasks'); self.git('commit', '-m', 'record evidence')
        self.assertTrue(self.check()['ready'])

    def test_wrong_repo_pr_head_and_draft_block(self):
        self.provider.pr['head'] = 'a' * 40
        self.assertIn('pr_commit_mismatch', self.check()['missing'])
        self.provider.pr['head'] = self.commit; self.provider.pr['draft'] = True
        self.assertIn('pr_not_deliverable', self.check()['missing'])
        self.contract['issue_url'] = 'https://github.com/other/project/issues/1'; self.save()
        self.assertFalse(self.check()['ready'])

    def test_platform_review_must_be_current_and_not_self_approval(self):
        self.contract['review_source'] = 'github_review'; self.save()
        self.assertIn('github_review', self.check()['missing'])
        review = {'state': 'APPROVED', 'user': {'login': 'reviewer'}, 'commit_id': self.commit, 'html_url': 'review-url'}
        self.provider.pr['reviews'] = [review]
        self.assertTrue(self.check()['ready'])
        review['commit_id'] = 'a' * 40
        self.assertIn('github_review', self.check()['missing'])
        review['commit_id'] = self.commit; review['user']['login'] = 'implementer'
        self.assertIn('github_review', self.check()['missing'])

    def test_requested_changes_blocks_even_recorded_review(self):
        self.provider.pr['reviews'] = [{'state': 'CHANGES_REQUESTED', 'user': {'login': 'reviewer'}}]
        self.assertIn('github_changes_requested', self.check()['missing'])

    def test_platform_checks_missing_failed_pending_or_other_sha_block(self):
        self.contract['check_source'] = 'github_checks'; self.save()
        self.assertFalse(self.check()['ready'])
        run = {'name': 'unit-tests', 'head_sha': self.commit, 'status': 'completed', 'conclusion': 'success', 'html_url': 'check-url'}
        self.provider.runs = [run]
        self.assertTrue(self.check()['ready'])
        for key, value in [('head_sha', 'a' * 40), ('status', 'in_progress'), ('conclusion', 'failure')]:
            previous = run[key]; run[key] = value
            self.assertFalse(self.check()['ready'])
            run[key] = previous

    def test_legacy_success_runner_does_not_pass_g4(self):
        self.meta['delivery_requirements']['require_runner'] = True
        self.meta['archive_evidence']['runner_refs'] = ['.trellis/tasks/demo-delivery/runner.json']
        (self.root / self.meta['archive_evidence']['runner_refs'][0]).write_text('{"status":"success"}', encoding='utf-8')
        self.save()
        self.assertTrue(self.check('G3')['ready'])
        self.assertIn('runner_legacy_unbound', self.check('G4')['missing'])

    def test_current_summary_and_input_binding_pass_but_changed_input_fails(self):
        self.meta['delivery_requirements']['require_runner'] = True
        input_path = self.root / '.trellis/tasks/demo-delivery/evidence/input.json'
        input_path.write_text('{"tasks": []}', encoding='utf-8')
        path = write_evidence_summary(self.root, self.commit)
        summary = json.loads(path.read_text(encoding='utf-8'))
        summary['artifacts']['input'] = {'present': True, 'bytes': len(input_path.read_bytes()),
                                        'sha256': hashlib.sha256(input_path.read_bytes()).hexdigest()}
        summary.pop('integrity')
        summary['integrity'] = {'algorithm': 'sha256', 'sha256': hashlib.sha256(c.canonical_json_bytes(summary)).hexdigest()}
        path.write_text(json.dumps(summary), encoding='utf-8')
        ref = path.relative_to(self.root).as_posix()
        self.meta['archive_evidence'].update(runner_refs=[ref], runner_inputs={ref: input_path.relative_to(self.root).as_posix()})
        self.save()
        self.assertTrue(self.check('G4')['ready'], self.check('G4'))
        input_path.write_text('{"changed": true}', encoding='utf-8')
        self.assertIn('runner_input_binding', self.check('G4')['missing'])

    def test_missing_ac_artifact_blocks_final_acceptance(self):
        self.meta['archive_evidence']['acceptance_criteria'][0]['evidence_refs'] = ['missing.txt']
        self.save()
        self.assertFalse(self.check('G5')['ready'])

    def test_gate_checks_before_any_history_write_and_accepts_valid_evidence(self):
        path = self.root / '.project-gates/project.json'
        project = c.read_json(path); project['current_gate'] = 'G3'; c.write_json_atomic(path, project)
        with mock.patch('delivery_guard.GitHub', return_value=self.provider):
            result = c.close_gate(gate_args(self.root, accepted_gate='G3'))
        self.assertTrue(result['ok'])
        self.assertEqual(c.read_json(path)['current_gate'], 'G4')

    def test_guarded_archive_runs_only_after_authorization_and_check(self):
        args = argparse.Namespace(project_root=str(self.root), task='demo-delivery', confirm_archive=False, user_accepted=False)
        with self.assertRaises(c.CollabError):
            c.delivery_archive(args)
        args.confirm_archive = True
        with mock.patch('delivery_guard.GitHub', return_value=self.provider):
            self.assertFalse(c.delivery_archive(args)['ok'])
        path = self.root / '.project-gates/project.json'
        project = c.read_json(path); project.update(current_gate='G5', status='operational'); c.write_json_atomic(path, project)
        scripts = self.root / '.trellis/scripts'; scripts.mkdir()
        # Isolated Trellis protocol fixture, not an invocation in a real business project.
        (scripts / 'task.py').write_text('''import sys, json, pathlib, shutil
assert sys.argv[1] == "archive" and sys.argv[-1] == "--no-commit"
root=pathlib.Path.cwd()
src=root/".trellis/tasks"/sys.argv[2]
value=json.loads((src/"task.json").read_text(encoding="utf-8"))
value["status"]="completed"
(src/"task.json").write_text(json.dumps(value),encoding="utf-8")
dest=root/".trellis/tasks/archive/2026-09"
dest.mkdir(parents=True)
shutil.move(str(src),str(dest/src.name))
''', encoding='utf-8')
        self.git('add', '.trellis/scripts'); self.git('commit', '-m', 'fixture archive tool')
        # Tool installation changes the deliverable, so bind all evidence to the new version.
        self.commit = self.git('rev-parse', 'HEAD').strip(); self.provider.pr['head'] = self.commit
        self.meta['archive_evidence'].update(commit=self.commit, review_ref=self.make_record('review'),
            check_refs={'unit-tests': self.make_record('local_check')}, acceptance_ref=self.make_record('user_acceptance'))
        self.save()
        before_gate = path.read_bytes()
        with mock.patch('delivery_guard.GitHub', return_value=self.provider):
            result = c.delivery_archive(args)
        self.assertTrue(result['ok'], result)
        self.assertFalse(self.task_path.exists())
        self.assertEqual(before_gate, path.read_bytes())

    def test_archive_requires_operational_project_and_complete_route(self):
        self.assertIn('project_not_operational', self.check('archive')['missing'])
        path = self.root / '.project-gates/project.json'; project = c.read_json(path)
        project.update(current_gate='G5', status='operational'); c.write_json_atomic(path, project)
        self.assertTrue(self.check('archive')['ready'])
        self.meta['delivery_route'] = {'change_class': 'bugfix', 'entry': 'G3', 'required_reviews': ['G3'],
                                      'completed_reviews': [], 'project_revalidations': []}
        self.save()
        self.assertIn('delivery_route_incomplete', self.check('archive')['missing'])

    def test_api_failure_never_falls_back_to_local_pass(self):
        with mock.patch.object(self.provider, 'issue', side_effect=EvidenceError('network unavailable')):
            self.assertFalse(self.check()['ready'])

    def test_g3_gate_cannot_bypass_missing_contract(self):
        del self.meta['delivery_contract']; self.save()
        path = self.root / '.project-gates/project.json'; project = c.read_json(path)
        project['current_gate'] = 'G3'; c.write_json_atomic(path, project)
        before = (self.root / '.project-gates/gate-history.md').read_bytes()
        with self.assertRaises(c.CollabError):
            c.close_gate(gate_args(self.root, accepted_gate='G3'))
        self.assertEqual(before, (self.root / '.project-gates/gate-history.md').read_bytes())

    def test_cli_failure_has_nonzero_exit_and_no_write(self):
        del self.meta['delivery_contract']; self.save()
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / 'rpa_collab.py'), '--project-root', str(self.root),
                                 '--task', 'demo-delivery', 'delivery-check'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 3)
        self.assertFalse(json.loads(result.stdout)['ready'])

    def test_github_comment_record_is_distinguished_from_formal_review(self):
        value = json.loads((self.root / self.meta['archive_evidence']['review_ref']).read_text(encoding='utf-8'))
        url = 'https://github.com/example/project/issues/1#issuecomment-44'
        with mock.patch('github_delivery.api', return_value={'html_url': url, 'user': {'login': 'account'},
                'updated_at': '2026-09-07T00:00:00Z', 'body': 'Review\n```rpa-evidence\n' + json.dumps(value) + '\n```'}):
            data, source = GitHub().comment_record(url, 'example/project', 1, 2)
        self.assertEqual(data['task_id'], 'demo-delivery')
        self.assertEqual(source['kind'], 'github_comment')
        with self.assertRaises(EvidenceError):
            github_url('https://github.com.evil/example/project/pull/2', 'pull')

    def test_github_reader_collects_all_pages(self):
        url = 'https://github.com/example/project/pull/2'
        value = {'html_url': url, 'head': {'sha': self.commit}, 'merged': False, 'state': 'open',
                 'created_at': '2026-09-07T00:00:00Z', 'user': {'login': 'author'}}
        with mock.patch('github_delivery.api', side_effect=[value, [[{'id': 1}], [{'id': 2}]]]):
            self.assertEqual([r['id'] for r in GitHub().pull(url)['reviews']], [1, 2])

    def test_edited_comment_and_unrelated_comment_rejected(self):
        url = 'https://github.com/example/project/issues/1#issuecomment-44'
        with mock.patch('github_delivery.api', return_value={'html_url': url, 'body': 'passed'}):
            with self.assertRaises(EvidenceError):
                GitHub().comment_record(url, 'example/project', 1, 2)
        with self.assertRaises(EvidenceError):
            GitHub().comment_record(url, 'example/project', 99, 2)

    def test_missing_artifact_can_resolve_unique_archive_but_not_ambiguity(self):
        ref = '.trellis/tasks/old/evidence/report.md'
        one = self.root / '.trellis/tasks/archive/2026-08/old/evidence/report.md'
        one.parent.mkdir(parents=True); one.write_text('report', encoding='utf-8')
        self.assertEqual(guard.local_file(self.root, ref), one)
        two = self.root / '.trellis/tasks/archive/2026-09/old/evidence/report.md'
        two.parent.mkdir(parents=True); two.write_text('other', encoding='utf-8')
        with self.assertRaises(EvidenceError):
            guard.local_file(self.root, ref)

    def test_task_change_during_api_read_blocks(self):
        original = self.provider.issue
        def changed(url):
            value = c.read_json(self.task_path); value['notes'] = 'concurrent edit'
            c.write_json_atomic(self.task_path, value)
            return original(url)
        with mock.patch.object(self.provider, 'issue', side_effect=changed):
            self.assertIn('task_changed_during_check', self.check()['missing'])


if __name__ == '__main__':
    unittest.main()
