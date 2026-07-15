import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_trellis_progress.py"
SPEC = importlib.util.spec_from_file_location("update_trellis_progress", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def make_args(project_root: Path, **overrides):
    values = {
        "project_root": str(project_root),
        "task": None,
        "kind": "checkpoint",
        "gate": "G3",
        "accepted_gate": None,
        "current_work": "Implement handler",
        "latest_checkpoint": "Tests passed",
        "next_action": "Run dry-run",
        "next_owner": "agent",
        "blocked": False,
        "block_reason": "",
        "evidence": ["tests/test_handler.py"],
        "checkpoint_id": "cp-test-001",
        "timestamp": "2026-07-15T14:30:00+08:00",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class UpdateTrellisProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.task_dir = self.project_root / ".trellis" / "tasks" / "07-15-demo"
        self.task_dir.mkdir(parents=True)
        (self.task_dir / "task.json").write_text(
            json.dumps(
                {
                    "id": "demo",
                    "status": "in_progress",
                    "meta": {"keep_me": {"value": 1}},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_updates_snapshot_and_preserves_existing_meta(self):
        result = MODULE.update_progress(make_args(self.project_root))
        task = json.loads((self.task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(task["meta"]["keep_me"], {"value": 1})
        self.assertEqual(task["meta"]["progress"]["current_gate"], "G3")
        self.assertIn("checkpoint:cp-test-001", (self.task_dir / "progress.md").read_text(encoding="utf-8"))

    def test_repeated_checkpoint_is_idempotent(self):
        args = make_args(self.project_root)
        MODULE.update_progress(args)
        MODULE.update_progress(args)
        history = (self.task_dir / "progress.md").read_text(encoding="utf-8")
        self.assertEqual(history.count("checkpoint:cp-test-001"), 1)

    def test_gate_close_requires_sequential_result_gate(self):
        args = make_args(
            self.project_root,
            kind="gate_close",
            accepted_gate="G2",
            gate="G4",
        )
        with self.assertRaises(MODULE.ProgressError):
            MODULE.update_progress(args)

    def test_blocked_checkpoint_requires_reason(self):
        args = make_args(self.project_root, blocked=True, block_reason="")
        with self.assertRaises(MODULE.ProgressError):
            MODULE.update_progress(args)

    def test_checkpoint_cannot_change_saved_gate(self):
        MODULE.update_progress(make_args(self.project_root))
        args = make_args(
            self.project_root,
            gate="G4",
            checkpoint_id="cp-test-002",
        )
        with self.assertRaises(MODULE.ProgressError):
            MODULE.update_progress(args)

    def test_gate_close_must_accept_saved_current_gate(self):
        MODULE.update_progress(make_args(self.project_root))
        args = make_args(
            self.project_root,
            kind="gate_close",
            accepted_gate="G2",
            gate="G3",
            checkpoint_id="cp-test-003",
        )
        with self.assertRaises(MODULE.ProgressError):
            MODULE.update_progress(args)

    def test_same_checkpoint_id_rejects_changed_content(self):
        MODULE.update_progress(make_args(self.project_root))
        args = make_args(self.project_root, next_action="Different next action")
        with self.assertRaises(MODULE.ProgressError):
            MODULE.update_progress(args)


if __name__ == "__main__":
    unittest.main()
