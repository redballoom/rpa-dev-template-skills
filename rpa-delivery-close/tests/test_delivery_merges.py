"""Small real-Git graphs covering merge false positives and required blockers."""
import tempfile
import unittest
from pathlib import Path
import importlib.util
from unittest import mock
import subprocess

COMPONENT = Path(__file__).resolve().parents[1]
MODULE_PATH = next(p for p in [COMPONENT / 'tools/delivery_version.py',
                              COMPONENT / 'scripts/delivery_version.py'] if p.exists())
SPEC = importlib.util.spec_from_file_location('merge_test_version', MODULE_PATH)
pinned = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pinned)
delivery_version = pinned.delivery_version


class MergePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Local test")
        self.git("config", "user.email", "local-test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.repo / "no-hooks"))
        self.commit("app.py", "original\n")
        self.initial = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-b", "business")
        self.commit("app.py", "accepted\n")
        self.baseline = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return pinned.git(self.repo, *args)

    def commit(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git("add", "--", path)
        self.git("commit", "-m", "test change")

    def merge_business(self):
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "business", "-m", "merge business")

    def assert_blocked(self):
        result = delivery_version(self.repo, self.baseline)
        self.assertTrue(not result["ok"] or not result["baseline_compatible"] or result["delivery_paths"], result)

    def test_two_pr_closeout(self):
        self.git("checkout", "-b", "evidence")
        self.commit(".project-gates/project.json", "{}\n")
        self.merge_business()
        self.git("merge", "--no-ff", "evidence", "-m", "merge evidence")
        self.assertTrue(delivery_version(self.repo, self.baseline)["baseline_compatible"])

    def test_new_code_after_acceptance(self):
        self.commit("app.py", "new\n")
        self.assert_blocked()

    def test_code_change_then_revert(self):
        self.commit("app.py", "new\n")
        self.git("revert", "--no-edit", "HEAD")
        self.assertEqual(self.git("diff", self.baseline, "HEAD"), "")
        self.assert_blocked()

    def test_side_branch_code_then_revert(self):
        self.git("checkout", "-b", "side", self.initial)
        self.commit("side.py", "new\n")
        self.git("revert", "--no-edit", "HEAD")
        self.git("checkout", "business")
        self.git("merge", "--no-ff", "side", "-m", "merge reverted side")
        self.assertEqual(self.git("diff", self.baseline, "HEAD"), "")
        self.assert_blocked()

    def test_old_branch_record_only(self):
        self.git("checkout", "-b", "records", self.initial)
        self.commit(".project-gates/project.json", "{}\n")
        self.git("checkout", "business")
        self.git("merge", "--no-ff", "records", "-m", "merge records")
        self.assertTrue(delivery_version(self.repo, self.baseline)["baseline_compatible"])

    def test_merge_introduces_code(self):
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "--no-commit", "business")
        self.commit("app.py", "merge-only edit\n")
        self.assert_blocked()

    def test_diverged_history(self):
        self.git("checkout", "main")
        self.assertFalse(delivery_version(self.repo, self.baseline)["ok"])

    def test_untracked_code(self):
        (self.repo / "unknown.py").write_text("new\n")
        self.assert_blocked()

    def test_staged_code_hidden_by_worktree(self):
        (self.repo / "app.py").write_text("new\n")
        self.git("add", "app.py")
        (self.repo / "app.py").write_text("accepted\n")
        self.assert_blocked()

    def test_renamed_code(self):
        self.git("mv", "app.py", "renamed.py")
        self.git("commit", "-m", "rename")
        self.assert_blocked()



    def test_git_parent_query_error_fails_closed(self):
        self.merge_business()
        original_git = pinned.git

        def broken_git(repo, *args):
            if args[:2] == ('merge-base', '--is-ancestor') and args[-1] == self.initial:
                raise subprocess.CalledProcessError(128, ['git', *args])
            return original_git(repo, *args)

        with mock.patch.object(pinned, 'git', side_effect=broken_git):
            result = delivery_version(self.repo, self.baseline)
        self.assertFalse(result['ok'])
        self.assertFalse(result['baseline_compatible'])

    def test_multiple_accepted_parents_and_records(self):
        self.git('checkout', '-b', 'records')
        self.commit('.project-gates/project.json', '{}\n')
        self.git('checkout', 'business')
        self.commit('.project-gates/gate-history.md', 'accepted\n')
        self.git('merge', '--no-ff', 'records', '-m', 'merge records')
        self.assertTrue(delivery_version(self.repo, self.baseline)['baseline_compatible'])

    def test_nonaccepted_side_merge_still_checks_code(self):
        self.git('checkout', '-b', 'side', self.initial)
        self.commit('side.py', 'new\n')
        self.git('checkout', '-b', 'side-records', self.initial)
        self.commit('.project-gates/project.json', '{}\n')
        self.git('checkout', 'side')
        self.git('merge', '--no-ff', 'side-records', '-m', 'merge outside baseline lineage')
        self.git('checkout', 'business')
        self.git('merge', '--no-ff', 'side', '-m', 'merge side')
        self.assert_blocked()


if __name__ == "__main__":
    unittest.main(verbosity=2)
