import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT_DIR / "hermes_controller.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("hermes_controller", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_workspace(project_root: Path) -> None:
    (project_root / ".trellis" / "spec").mkdir(parents=True, exist_ok=True)
    (project_root / ".trellis" / "config.yaml").write_text(
        "workspace:\n  developer: test\n# session_auto_commit: true\n",
        encoding="utf-8",
    )
    write_task(
        project_root,
        "00-bootstrap-guidelines",
        status="in_progress",
        meta={},
    )


def write_task(
    project_root: Path,
    task_id: str = "demo-delivery",
    *,
    status: str = "planning",
    meta: dict | None = None,
    acceptance_criteria: list[str] | None = None,
    technical_checks: list[str] | None = None,
    commit: str | None = None,
    pr_url: str | None = None,
) -> Path:
    task_dir = project_root / ".trellis" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": task_id,
        "name": task_id,
        "status": status,
        "meta": meta or {},
    }
    if acceptance_criteria is not None:
        data["acceptance_criteria"] = acceptance_criteria
    if technical_checks is not None:
        data["technical_checks"] = technical_checks
    if commit is not None:
        data["commit"] = commit
    if pr_url is not None:
        data["pr_url"] = pr_url
    (task_dir / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_dir


def bootstrap_args(project_root: Path, **overrides: object) -> argparse.Namespace:
    values = {
        "project_root": str(project_root),
        "task": None,
        "project_name": "Demo Project",
        "task_id": "demo-delivery",
        "task_name": "Demo Delivery",
        "initial_gate": "G0",
        "allow_minimal": False,
        "init_trellis": False,
        "trellis_cmd": None,
        "trellis_registry": MODULE.DEFAULT_TRELLIS_REGISTRY,
        "trellis_template": MODULE.DEFAULT_TRELLIS_TEMPLATE,
        "trellis_codex": True,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def gate_args(project_root: Path, **overrides: object) -> argparse.Namespace:
    values = {
        "project_root": str(project_root),
        "task": "demo-delivery",
        "accepted_gate": "G0",
        "gate": "G2",
        "evidence": ["AGENTS.md"],
        "timestamp": "2026-08-14T10:00:00+08:00",
        "event_id": "gate-close-g0-test",
        "reason": "User accepted the scope",
        "confirm_user_acceptance": True,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class HermesControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        write_workspace(self.project_root)
        (self.project_root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def init_git(self) -> str:
        subprocess.run(["git", "init"], cwd=self.project_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.project_root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.project_root, check=True)
        subprocess.run(["git", "add", "AGENTS.md"], cwd=self.project_root, check=True)
        subprocess.run(["git", "commit", "-m", "test evidence"], cwd=self.project_root, check=True, capture_output=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_safe_config_is_explicit_and_idempotent(self) -> None:
        first = MODULE.ensure_trellis_safe_config(self.project_root)
        second = MODULE.ensure_trellis_safe_config(self.project_root)
        text = (self.project_root / ".trellis" / "config.yaml").read_text(encoding="utf-8")
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertIn("workspace:\n", text)
        self.assertEqual(text.count("session_auto_commit: false"), 1)

    def test_published_schemas_are_valid_json(self) -> None:
        references = Path(__file__).resolve().parents[1] / "references"
        project_schema = json.loads((references / "hermes-project.schema.json").read_text(encoding="utf-8"))
        delivery_schema = json.loads((references / "trellis-delivery.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(project_schema["properties"]["schema_version"]["const"], 1)
        self.assertIn("archive_evidence", delivery_schema["properties"])

    def test_bootstrap_creates_hermes_and_task_without_task_gate_state(self) -> None:
        result = MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project = json.loads((self.project_root / ".hermes" / "project.json").read_text(encoding="utf-8"))
        task = json.loads((self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(project["current_gate"], "G0")
        self.assertEqual(task["status"], "planning")
        self.assertNotIn("progress", task["meta"])
        self.assertFalse((self.project_root / ".trellis" / "tasks" / "demo-delivery" / "progress.md").exists())
        self.assertTrue(result["trellis_config"]["verified"])

    def test_bootstrap_rejects_missing_explicit_task_instead_of_creating_another(self) -> None:
        with self.assertRaises(MODULE.CollabError):
            MODULE.bootstrap_collaboration(
                bootstrap_args(self.project_root, task="missing-task", task_id="unexpected-task")
            )
        self.assertFalse(
            (self.project_root / ".trellis" / "tasks" / "unexpected-task" / "task.json").exists()
        )

    def test_status_combines_hermes_task_git_runner_and_detects_legacy(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        task_file = self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json"
        task = json.loads(task_file.read_text(encoding="utf-8"))
        task["meta"]["progress"] = {"current_gate": "G0"}
        task_file.write_text(json.dumps(task), encoding="utf-8")
        (self.project_root / "runner_demo.json").write_text('{"run_id":"demo","status":"success"}', encoding="utf-8")
        status = MODULE.build_status(self.project_root)
        self.assertEqual(status["hermes"]["current_gate"], "G0")
        self.assertEqual(status["selected_task"]["id"], "demo-delivery")
        self.assertEqual(status["runner"]["status"], "success")
        self.assertIn("legacy_gate_records", {item["code"] for item in status["warnings"]})

    def test_gate_close_requires_explicit_confirmation(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(gate_args(self.project_root, confirm_user_acceptance=False))

    def test_gate_close_advances_hermes_without_writing_task_progress(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        result = MODULE.close_gate(gate_args(self.project_root))
        task = json.loads((self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(encoding="utf-8"))
        history = (self.project_root / ".hermes" / "gate-history.md").read_text(encoding="utf-8")
        self.assertEqual(result["read_back"]["current_gate"], "G1")
        self.assertIn("- event: gate-close", history)
        self.assertIn("- gate: G0", history)
        self.assertNotIn("progress", task["meta"])

    def test_gate_close_rejects_second_close_of_same_gate(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root))
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(gate_args(self.project_root, event_id="second"))

    def test_g5_close_becomes_operational_and_revalidation_keeps_g5(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".hermes" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G5"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        close_result = MODULE.close_gate(gate_args(self.project_root, accepted_gate="G5", event_id="g5-close"))
        self.assertEqual(close_result["read_back"]["status"], "operational")
        revalidate = gate_args(
            self.project_root,
            gate="G2",
            reason="Major contract change accepted",
            event_id="g2-revalidation",
        )
        result = MODULE.revalidate_gate(revalidate)
        self.assertEqual(result["read_back"]["current_gate"], "G5")
        self.assertTrue(result["current_gate_unchanged"])
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(gate_args(self.project_root, accepted_gate="G5", event_id="g5-second-close"))

    def test_archive_guard_rejects_missing_contract_and_evidence(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertFalse(result["ready"])
        self.assertEqual(
            set(result["missing"]),
            {"acceptance_criteria", "technical_checks", "commit", "final_summary"},
        )

    def test_archive_guard_passes_configured_requirements(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        commit = self.init_git()
        meta = {
            "delivery_requirements": {
                "require_pr": True,
                "require_runner": True,
                "require_user_acceptance": True,
            },
            "archive_evidence": {
                "acceptance_criteria": [
                    {"id": "AC1", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                ],
                "technical_checks": [
                    {"name": "unit tests", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                ],
                "commit": commit,
                "pr_url": "https://example.test/pr/1",
                "runner_refs": ["runner_delivery.json"],
                "user_acceptance": True,
                "final_summary": "Contract and implementation evidence verified.",
            },
        }
        write_task(
            self.project_root,
            meta=meta,
        )
        (self.project_root / "runner_delivery.json").write_text('{"status":"success"}', encoding="utf-8")
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=True)
        result = MODULE.archive_check(args)
        self.assertTrue(result["ready"])
        self.assertEqual(result["missing"], [])

    def test_archive_guard_rejects_already_completed_task(self) -> None:
        write_task(self.project_root, status="completed")
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertIn("task_already_archived", result["missing"])

    def test_migration_preview_never_writes_hermes(self) -> None:
        task_dir = write_task(self.project_root, meta={"progress": {"current_gate": "G3"}})
        (task_dir / "progress.md").write_text("# Legacy\n", encoding="utf-8")
        args = argparse.Namespace(project_root=str(self.project_root))
        result = MODULE.migration_preview(args)
        self.assertFalse(result["write_performed"])
        self.assertEqual(len(result["legacy_records"]), 2)
        self.assertFalse((self.project_root / ".hermes").exists())


if __name__ == "__main__":
    unittest.main()
