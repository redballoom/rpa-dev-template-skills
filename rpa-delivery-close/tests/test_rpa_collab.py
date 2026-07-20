import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT_DIR / "rpa_collab.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("rpa_collab", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_task(task_dir: Path, *, status="in_progress", gate="G2", next_owner="agent", archived=False):
    if archived:
        task_dir = task_dir / "archive" / "2026-07" / "07-20-demo"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "status": status,
                "meta": {
                    "progress": {
                        "schema_version": 1,
                        "current_gate": gate,
                        "current_work": "Current work",
                        "latest_checkpoint": "Latest checkpoint",
                        "next_action": "Next action",
                        "next_owner": next_owner,
                        "blocked": False,
                        "block_reason": "",
                        "updated_at": "2026-07-20T10:00:00+08:00",
                        "checkpoint_id": "cp-existing",
                        "evidence_refs": [],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return task_dir


def write_full_trellis_workspace(project_root: Path):
    spec_dir = project_root / ".trellis" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "README.md").write_text("# Test Spec\n", encoding="utf-8")


def make_write_args(project_root: Path, **overrides):
    values = {
        "project_root": str(project_root),
        "task": None,
        "accepted_gate": "G2",
        "gate": None,
        "current_work": "G2 accepted",
        "latest_checkpoint": "Contract confirmed",
        "next_action": "Implement handler",
        "next_owner": "agent",
        "blocked": False,
        "block_reason": "",
        "evidence": ["docs/SHADOWBOT_INPUT_CONTRACT.md"],
        "checkpoint_id": "cp-g2-close",
        "timestamp": "2026-07-20T10:30:00+08:00",
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def make_bootstrap_args(project_root: Path, **overrides):
    values = {
        "project_root": str(project_root),
        "task": None,
        "project_name": "Demo Project",
        "task_id": "demo-delivery",
        "task_name": "Demo Delivery",
        "initial_gate": "G0",
        "current_work": "Collaboration bootstrap initialized",
        "latest_checkpoint": "Project ready for G0",
        "next_action": "Align requirement scope",
        "next_owner": "agent",
        "evidence": ["AGENTS.md"],
        "checkpoint_id": "cp-bootstrap",
        "timestamp": "2026-07-20T09:00:00+08:00",
        "dry_run": False,
        "init_trellis": False,
        "trellis_cmd": None,
        "trellis_registry": MODULE.DEFAULT_TRELLIS_REGISTRY,
        "trellis_template": MODULE.DEFAULT_TRELLIS_TEMPLATE,
        "trellis_codex": True,
        "allow_minimal": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class RpaCollabTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.tasks_root = self.project_root / ".trellis" / "tasks"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_reads_current_progress(self):
        task_dir = write_task(self.tasks_root / "07-20-demo", gate="G3")
        result = MODULE.build_status(self.project_root)
        self.assertEqual(Path(result["task_file"]).resolve(), (task_dir / "task.json").resolve())
        self.assertEqual(result["progress"]["current_gate"], "G3")
        self.assertEqual(result["warnings"], [])

    def test_suggest_recovery_when_completed_task_has_active_owner(self):
        write_task(self.tasks_root / "07-20-demo", status="completed", gate="G5", next_owner="user")
        status = MODULE.build_status(self.project_root)
        suggestion = MODULE.suggest_action(status)
        self.assertIn("lifecycle_drift", {warning["code"] for warning in status["warnings"]})
        self.assertEqual(suggestion["recommended_action"], "recovery")

    def test_bootstrap_requires_full_trellis_workspace_by_default(self):
        with self.assertRaises(MODULE.CollabError):
            MODULE.bootstrap_collaboration(make_bootstrap_args(self.project_root))

    def test_bootstrap_creates_task_and_initial_progress_when_spec_exists(self):
        write_full_trellis_workspace(self.project_root)
        result = MODULE.bootstrap_collaboration(make_bootstrap_args(self.project_root))
        self.assertTrue(result["ok"])
        self.assertTrue(result["created_task"])
        self.assertTrue(result["initialized_progress"])
        self.assertEqual(result["trellis_workspace"], "full")
        self.assertEqual(result["status"]["progress"]["current_gate"], "G0")
        self.assertEqual(result["status"]["progress"]["next_action"], "Align requirement scope")
        self.assertEqual(result["suggestion"]["recommended_action"], "continue_current_gate")
        self.assertTrue((self.tasks_root / "demo-delivery" / "progress.md").exists())

    def test_bootstrap_is_idempotent_when_progress_exists(self):
        write_full_trellis_workspace(self.project_root)
        MODULE.bootstrap_collaboration(make_bootstrap_args(self.project_root))
        result = MODULE.bootstrap_collaboration(
            make_bootstrap_args(
                self.project_root,
                initial_gate="G1",
                current_work="Different work that should not overwrite",
                checkpoint_id="cp-bootstrap-second",
            )
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["initialized_progress"])
        self.assertEqual(result["status"]["progress"]["current_gate"], "G0")
        self.assertEqual(result["status"]["progress"]["current_work"], "Collaboration bootstrap initialized")
        history = (self.tasks_root / "demo-delivery" / "progress.md").read_text(encoding="utf-8")
        self.assertNotIn("cp-bootstrap-second", history)

    def test_bootstrap_allows_minimal_only_when_explicit(self):
        result = MODULE.bootstrap_collaboration(make_bootstrap_args(self.project_root, allow_minimal=True))
        self.assertTrue(result["ok"])
        self.assertEqual(result["trellis_workspace"], "minimal")
        self.assertTrue(result["created_task"])

    def test_bootstrap_init_trellis_dry_run_plans_command(self):
        result = MODULE.bootstrap_collaboration(
            make_bootstrap_args(self.project_root, init_trellis=True, trellis_cmd="trellis.cmd", dry_run=True)
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["trellis_workspace"], "full")
        self.assertEqual(result["trellis_init"]["command"][:2], ["trellis.cmd", "init"])

    def test_gate_close_checks_saved_gate_before_writing(self):
        write_task(self.tasks_root / "07-20-demo", gate="G2")
        result = MODULE.close_gate(make_write_args(self.project_root))
        self.assertTrue(result["ok"])
        self.assertEqual(result["read_back"]["progress"]["current_gate"], "G3")
        history = (self.tasks_root / "07-20-demo" / "progress.md").read_text(encoding="utf-8")
        self.assertIn("Accepted Gate: `G2`", history)

    def test_gate_close_rejects_stale_acceptance(self):
        write_task(self.tasks_root / "07-20-demo", gate="G3")
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(make_write_args(self.project_root, accepted_gate="G2"))

    def test_finish_aligns_g5_progress_and_completed_status(self):
        write_task(self.tasks_root / "07-20-demo", gate="G5")
        args = make_write_args(
            self.project_root,
            accepted_gate="G5",
            current_work="Final calibration complete",
            latest_checkpoint="User accepted delivery",
            next_action="No further local action",
            evidence=["runner_g5.json", "commit:abc1234"],
            checkpoint_id="cp-g5-finish",
        )
        result = MODULE.finish(args)
        self.assertTrue(result["ok"])
        self.assertEqual(result["read_back"]["task_status"], "completed")
        self.assertEqual(result["read_back"]["progress"]["current_gate"], "G5")
        self.assertEqual(result["read_back"]["progress"]["next_owner"], "none")
        self.assertNotIn("lifecycle_drift", {warning["code"] for warning in result["read_back"]["warnings"]})

    def test_finish_requires_g5(self):
        write_task(self.tasks_root / "07-20-demo", gate="G4")
        with self.assertRaises(MODULE.CollabError):
            MODULE.finish(make_write_args(self.project_root))


if __name__ == "__main__":
    unittest.main()
