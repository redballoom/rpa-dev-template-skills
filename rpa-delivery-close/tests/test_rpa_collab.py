import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPT_DIR / "project_gate_controller.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("project_gate_controller", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
CLI_SPEC = importlib.util.spec_from_file_location("rpa_collab", SCRIPT_DIR / "rpa_collab.py")
CLI_MODULE = importlib.util.module_from_spec(CLI_SPEC)
assert CLI_SPEC and CLI_SPEC.loader
CLI_SPEC.loader.exec_module(CLI_MODULE)


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


def route_args(project_root: Path, **overrides: object) -> argparse.Namespace:
    values = {
        "project_root": str(project_root),
        "task": "demo-delivery",
        "change_class": "bugfix",
        "entry": "G3",
        "require_review": ["G3", "G4", "G5"],
        "complete_review": [],
        "project_revalidation": [],
        "confirm_delivery_route": True,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_legacy_project_gate(project_root: Path) -> None:
    legacy_dir = project_root / ".hermes"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "demo-project",
                "current_gate": "G3",
                "status": "active",
                "updated_at": "2026-08-17T10:00:00+08:00",
            }
        ),
        encoding="utf-8",
    )
    (legacy_dir / "gate-history.md").write_text("# Gate History\n\n", encoding="utf-8")


class ProjectGateControllerTests(unittest.TestCase):
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
        project_schema = json.loads((references / "project-gate.schema.json").read_text(encoding="utf-8"))
        delivery_schema = json.loads((references / "trellis-delivery.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(project_schema["properties"]["schema_version"]["const"], 1)
        self.assertIn("archive_evidence", delivery_schema["properties"])
        self.assertIn("delivery_route", delivery_schema["properties"])
        self.assertEqual(delivery_schema["properties"]["delivery_route"]["properties"]["entry"]["$ref"], "#/$defs/deliveryReview")
        self.assertEqual(
            set(delivery_schema["properties"]["delivery_requirements"]["required"]),
            {"require_pr", "require_runner", "require_user_acceptance"},
        )

    def test_bootstrap_creates_project_gate_and_task_without_task_gate_state(self) -> None:
        result = MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project = json.loads((self.project_root / ".project-gates" / "project.json").read_text(encoding="utf-8"))
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

    def test_status_combines_project_gate_task_git_runner_and_detects_legacy(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        task_file = self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json"
        task = json.loads(task_file.read_text(encoding="utf-8"))
        task["meta"]["progress"] = {"current_gate": "G0"}
        task_file.write_text(json.dumps(task), encoding="utf-8")
        (self.project_root / "runner_demo.json").write_text('{"run_id":"demo","status":"success"}', encoding="utf-8")
        status = MODULE.build_status(self.project_root)
        self.assertEqual(status["project_gate"]["current_gate"], "G0")
        self.assertEqual(status["selected_task"]["id"], "demo-delivery")
        self.assertEqual(status["runner"]["status"], "success")
        self.assertIn("legacy_gate_records", {item["code"] for item in status["warnings"]})

    def test_delivery_route_is_optional_for_legacy_task(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        result = MODULE.check_delivery_route(self.project_root, "demo-delivery")
        self.assertTrue(result["ok"])
        self.assertFalse(result["present"])
        self.assertTrue(result["legacy_compatible"])

    def test_cli_exposes_structured_delivery_route_commands(self) -> None:
        checked = CLI_MODULE.build_parser().parse_args(
            ["--project-root", str(self.project_root), "--task", "demo-delivery", "delivery-route-check"]
        )
        written = CLI_MODULE.build_parser().parse_args(
            [
                "--project-root", str(self.project_root),
                "--task", "demo-delivery",
                "delivery-route-set",
                "--change-class", "bugfix",
                "--entry", "G3",
                "--require-review", "G3",
                "--confirm-delivery-route",
            ]
        )
        self.assertEqual(checked.command, "delivery-route-check")
        self.assertEqual(written.require_review, ["G3"])
        self.assertTrue(written.confirm_delivery_route)

    def test_delivery_route_set_requires_confirmation_and_preserves_project_gate(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        before = MODULE.read_project_gate(self.project_root)
        with self.assertRaises(MODULE.CollabError):
            MODULE.set_delivery_route(route_args(self.project_root, confirm_delivery_route=False))

        result = MODULE.set_delivery_route(route_args(self.project_root))

        task = json.loads((self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(result["read_back"]["entry"], "G3")
        self.assertEqual(result["read_back"]["required_reviews"], ["G3", "G4", "G5"])
        self.assertEqual(MODULE.read_project_gate(self.project_root), before)
        self.assertNotIn("current_gate", task["meta"]["delivery_route"])

    def test_delivery_route_revalidations_require_operational_g5(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        args = route_args(
            self.project_root,
            entry="G2",
            require_review=["G2", "G3", "G4", "G5"],
            project_revalidation=["G2", "G4", "G5"],
        )
        with self.assertRaises(MODULE.CollabError):
            MODULE.set_delivery_route(args)

        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update({"current_gate": "G5", "status": "operational"})
        project_path.write_text(json.dumps(project), encoding="utf-8")
        result = MODULE.set_delivery_route(args)
        self.assertEqual(result["read_back"]["project_revalidations"], ["G2", "G4", "G5"])
        self.assertEqual(MODULE.read_project_gate(self.project_root)["current_gate"], "G5")

    def test_delivery_route_rejects_trellis_set_meta_string(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        task_file = self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json"
        task = json.loads(task_file.read_text(encoding="utf-8"))
        task["meta"]["delivery_route"] = '{"entry":"G3"}'
        task_file.write_text(json.dumps(task), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.CollabError, "JSON object"):
            MODULE.check_delivery_route(self.project_root, "demo-delivery")
        status = MODULE.build_status(self.project_root, "demo-delivery")
        self.assertIn("invalid_delivery_route", {item["code"] for item in status["warnings"]})

    def test_gate_close_requires_explicit_confirmation(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(gate_args(self.project_root, confirm_user_acceptance=False))

    def test_gate_close_advances_project_gate_without_writing_task_progress(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        result = MODULE.close_gate(gate_args(self.project_root))
        task = json.loads((self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(encoding="utf-8"))
        history = (self.project_root / ".project-gates" / "gate-history.md").read_text(encoding="utf-8")
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
        project_path = self.project_root / ".project-gates" / "project.json"
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
            {
                "acceptance_criteria",
                "technical_checks",
                "commit",
                "delivery_requirements",
                "final_summary",
            },
        )

    def test_archive_guard_rejects_incomplete_delivery_requirements(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        write_task(
            self.project_root,
            meta={
                "delivery_requirements": {
                    "require_pr": False,
                    "require_runner": "false",
                }
            },
        )
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertIn("delivery_requirements.require_runner", result["missing"])
        self.assertIn("delivery_requirements.require_user_acceptance", result["missing"])

    def test_archive_guard_allows_explicit_false_pr_without_pr_url(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        commit = self.init_git()
        write_task(
            self.project_root,
            meta={
                "delivery_requirements": {
                    "require_pr": False,
                    "require_runner": False,
                    "require_user_acceptance": False,
                },
                "archive_evidence": {
                    "acceptance_criteria": [
                        {"id": "AC1", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                    ],
                    "technical_checks": [
                        {"name": "docs", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                    ],
                    "commit": commit,
                    "final_summary": "Explicitly approved delivery requirements need no PR evidence.",
                },
            },
        )
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertTrue(result["ready"])
        self.assertNotIn("pr_url", result["missing"])

    def test_archive_guard_requires_pr_url_when_pr_is_required(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        commit = self.init_git()
        write_task(
            self.project_root,
            meta={
                "delivery_requirements": {
                    "require_pr": True,
                    "require_runner": False,
                    "require_user_acceptance": False,
                },
                "archive_evidence": {
                    "acceptance_criteria": [
                        {"id": "AC1", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                    ],
                    "technical_checks": [
                        {"name": "unit tests", "result": "passed", "evidence_refs": ["AGENTS.md"]}
                    ],
                    "commit": commit,
                    "final_summary": "Implementation is ready for PR review.",
                },
            },
        )
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertFalse(result["ready"])
        self.assertEqual(result["missing"], ["pr_url"])

    def test_archive_guard_enforces_runner_and_user_acceptance_requirements(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        commit = self.init_git()
        write_task(
            self.project_root,
            meta={
                "delivery_requirements": {
                    "require_pr": False,
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
                    "final_summary": "Technical work is complete; target evidence is pending.",
                },
            },
        )
        args = argparse.Namespace(project_root=str(self.project_root), task="demo-delivery", user_accepted=False)
        result = MODULE.archive_check(args)
        self.assertEqual(set(result["missing"]), {"runner_evidence", "user_acceptance"})

    def test_archive_guard_passes_configured_requirements(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        commit = self.init_git()
        meta = {
            "delivery_route": {
                "change_class": "bugfix",
                "entry": "G3",
                "required_reviews": ["G3", "G4", "G5"],
                "completed_reviews": ["G3", "G4", "G5"],
                "project_revalidations": [],
            },
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

    def test_migration_preview_never_writes_project_gate(self) -> None:
        task_dir = write_task(self.project_root, meta={"progress": {"current_gate": "G3"}})
        (task_dir / "progress.md").write_text("# Legacy\n", encoding="utf-8")
        args = argparse.Namespace(project_root=str(self.project_root))
        result = MODULE.migration_preview(args)
        self.assertFalse(result["write_performed"])
        self.assertEqual(len(result["legacy_records"]), 2)
        self.assertFalse((self.project_root / ".project-gates").exists())

    def test_legacy_hermes_gate_files_block_bootstrap(self) -> None:
        write_legacy_project_gate(self.project_root)
        status = MODULE.build_status(self.project_root)
        codes = {item["code"] for item in status["warnings"]}
        self.assertIn("legacy_project_gate_directory", codes)
        self.assertIsNone(status["project_gate"])
        self.assertEqual(MODULE.suggest_action(status)["recommended_action"], "migrate_project_gates")
        with self.assertRaises(MODULE.CollabError):
            MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        self.assertFalse((self.project_root / ".project-gates").exists())

    def test_project_gate_migration_requires_confirmation(self) -> None:
        write_legacy_project_gate(self.project_root)
        args = argparse.Namespace(
            project_root=str(self.project_root),
            confirm_migration=False,
            timestamp="2026-08-17T12:00:00+08:00",
            dry_run=False,
        )
        with self.assertRaises(MODULE.CollabError):
            MODULE.migrate_project_gates(args)

    def test_current_and_legacy_gate_states_require_manual_conflict_resolution(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        write_legacy_project_gate(self.project_root)
        status = MODULE.build_status(self.project_root)
        self.assertEqual(
            MODULE.suggest_action(status)["recommended_action"],
            "resolve_project_gate_conflict",
        )
        preview = MODULE.migration_preview(argparse.Namespace(project_root=str(self.project_root)))
        self.assertIn("will not merge", preview["actions"][0])
        args = argparse.Namespace(
            project_root=str(self.project_root),
            confirm_migration=True,
            timestamp="2026-08-17T12:00:00+08:00",
            dry_run=False,
        )
        with self.assertRaises(MODULE.CollabError):
            MODULE.migrate_project_gates(args)

    def test_project_gate_migration_preserves_hermes_agent_plugins(self) -> None:
        write_legacy_project_gate(self.project_root)
        plugin_dir = self.project_root / ".hermes" / "plugins" / "sample"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text("name: sample\n", encoding="utf-8")
        args = argparse.Namespace(
            project_root=str(self.project_root),
            confirm_migration=True,
            timestamp="2026-08-17T12:00:00+08:00",
            dry_run=False,
        )

        result = MODULE.migrate_project_gates(args)

        self.assertTrue(result["ok"])
        self.assertEqual(result["project"]["current_gate"], "G3")
        self.assertFalse((self.project_root / ".hermes" / "project.json").exists())
        self.assertFalse((self.project_root / ".hermes" / "gate-history.md").exists())
        self.assertTrue((plugin_dir / "plugin.yaml").exists())
        history = (self.project_root / ".project-gates" / "gate-history.md").read_text(encoding="utf-8")
        self.assertIn("controller-storage-migration", history)
        self.assertIn("from: .hermes/", history)


if __name__ == "__main__":
    unittest.main()
