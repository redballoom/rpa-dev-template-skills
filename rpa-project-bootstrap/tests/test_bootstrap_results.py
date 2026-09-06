"""RF2: real CLI, local Git template and non-destructive recovery checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/init_rpa_project.py'
GOOD = 'print(\'{"status":"ok"}\')\n'

class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rf2-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'template'
        self.source.mkdir()
        self.target = self.root / '中文测试项目'
        for name in ['AGENTS.md', 'README.md', 'runner.py', 'run.bat', 'docs/OPERATION_GUIDE.md',
                     'docs/SHADOWBOT_INPUT_CONTRACT.md', 'docs/RPA_PYTHON_BOUNDARY.md',
                     'docs/examples/example.json', 'tests/test_example.py']:
            p = self.source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('开发模板\n', encoding='utf-8')
        (self.source / 'project.template.json').write_text(json.dumps({'project':'开发模板','token':'test-secret'}))
        (self.source / '.gitignore').write_text('project.json\n')
        (self.source / 'tools').mkdir()
        (self.source / 'tools/doctor.py').write_text(GOOD)
        self.git('init')
        self.git('config', 'user.name', 'RF2 Test')
        self.git('config', 'user.email', 'test@example.invalid')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git','-C',str(self.source),*args], check=True,
                              capture_output=True,text=True).stdout.strip()

    def launch(self, *extra, env=None):
        if self.git('status','--porcelain'):
            self.git('add','.')
            self.git('commit','-m','test template')
        p = subprocess.run([sys.executable,str(SCRIPT),'--name','中文测试项目','--target',str(self.target),
                            '--template-url',str(self.source),*extra], capture_output=True,
                           encoding='utf-8',env=env,timeout=30)
        return p.returncode, json.loads(p.stdout or p.stderr)

    def test_success_records_source_and_creates_new_history(self):
        code,r = self.launch()
        self.assertEqual((code,r['status'],r['verification']),(0,'success','passed'))
        self.assertEqual(r['template_commit'],self.git('rev-parse','HEAD'))
        self.assertEqual(json.loads((self.target/'project.json').read_text(encoding='utf-8'))['token'],'')
        count = subprocess.check_output(['git','-C',str(self.target),'rev-list','--count','HEAD'],text=True)
        self.assertEqual(count.strip(),'1')

    def test_missing_file_no_commit_then_recheck_preserves_user_changes(self):
        (self.source/'runner.py').unlink()
        code,r = self.launch()
        self.assertEqual((code,r['stage']),(1,'required_files'))
        self.assertIn('runner.py',r['missing_template_files'])
        self.assertFalse((self.target/'.git').exists())
        (self.target/'runner.py').write_text('# repaired\n')
        (self.target/'project.json').write_text('{"token":"preserve-local-config"}')
        def hashes():
            return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.target.rglob('*') if p.is_file()}
        before=hashes()
        code,r = self.launch('--verify-existing')
        self.assertEqual((code,r['status']),(0,'verified'))
        self.assertFalse(r['target_modified'])
        self.assertEqual(before,hashes())
        self.assertFalse((self.target/'.git').exists())

    def test_doctor_failures_never_report_success(self):
        for i,body in enumerate(['import sys\nsys.exit(1)\n','print("not JSON")\n','print(\'{"status":"failed"}\')\n']):
            with self.subTest(body=body):
                self.target=self.root/str(i)
                (self.source/'tools/doctor.py').write_text(body)
                code,r=self.launch()
                self.assertEqual((code,r['stage'],r['verification']),(1,'doctor','failed'))
                self.assertFalse((self.target/'.git').exists())

    def test_missing_doctor_and_skip_are_unverified(self):
        code,r=self.launch('--skip-post-checks')
        self.assertEqual((code,r['status'],r['verification']),(2,'incomplete','unverified'))
        self.assertFalse((self.target/'.git').exists())
        self.target=self.root/'missing-doctor'
        (self.source/'tools/doctor.py').unlink()
        code,r=self.launch()
        self.assertEqual((code,r['status']),(2,'incomplete'))
        self.assertFalse((self.target/'.git').exists())

    def test_nonempty_retry_preserves_files(self):
        self.target.mkdir()
        (self.target/'keep.txt').write_text('keep')
        code,r=self.launch()
        self.assertEqual((code,r['stage']),(1,'preflight'))
        self.assertFalse(r['target_modified'])
        self.assertEqual((self.target/'keep.txt').read_text(),'keep')

    def test_git_failure_preserves_verified_files_and_index(self):
        env=os.environ.copy()
        env.update(GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='user.name',GIT_CONFIG_VALUE_0='',
                   GIT_CONFIG_KEY_1='user.email',GIT_CONFIG_VALUE_1='')
        code,r=self.launch(env=env)
        self.assertEqual((code,r['stage'],r['verification']),(1,'git','passed'))
        self.assertTrue((self.target/'.git/index').exists())
        self.assertIn('Inspect Git',r['recovery']['git_recovery'])
        code,r=self.launch('--verify-existing')
        self.assertEqual((code,r['status'],r['git_commit']),(0,'verified',''))

    def test_clone_failure_leaves_target_absent(self):
        code,r=self.launch('--template-url',str(self.root/'absent'))
        self.assertEqual((code,r['stage']),(1,'clone'))
        self.assertFalse(self.target.exists())

    def test_verify_rejects_overwrite(self):
        self.target.mkdir()
        code,r=self.launch('--verify-existing','--force-overwrite')
        self.assertEqual((code,r['stage']),(1,'preflight'))

    def test_wrong_file_type_fails(self):
        (self.source/'runner.py').unlink()
        (self.source/'runner.py').mkdir()
        (self.source/'runner.py/placeholder').write_text('wrong type')
        code,r=self.launch()
        self.assertEqual(code,1)
        self.assertIn('runner.py',r['missing_template_files'])

    def test_invalid_config_reports_partial_configure_without_commit(self):
        (self.source/'project.template.json').write_text('{broken')
        code,r=self.launch()
        self.assertEqual((code,r['stage']),(1,'configure'))
        self.assertTrue(r['target_modified'])
        self.assertTrue((self.target/'README.md').exists())
        self.assertFalse((self.target/'.git').exists())

    def test_explicit_skip_git_still_requires_verification(self):
        code,r=self.launch('--skip-git')
        self.assertEqual((code,r['status'],r['verification']),(0,'success','passed'))
        self.assertEqual(r['git_commit'],'')
        self.assertFalse((self.target/'.git').exists())

    def test_empty_name_returns_structured_error(self):
        code,r=self.launch('--name','  ')
        self.assertEqual((code,r['stage']),(1,'preflight'))
        self.assertFalse(self.target.exists())

if __name__=='__main__':
    unittest.main()
