import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


def write_evidence_summary(
    project_root: Path,
    commit: str,
    *,
    status: str = "success",
    clean: bool = True,
    entrypoint: str = "run.bat",
    run_id: str = "portable-001",
) -> Path:
    summary = {
        "schema_version": 1,
        "run": {
            "run_id": run_id,
            "status": status,
            "started_at": "2026-09-05T00:00:00Z",
            "finished_at": "2026-09-05T00:00:01Z",
            "commit": commit,
            "working_tree_clean": clean,
        },
        "runtime": {
            "entrypoint": entrypoint,
            "interpreter": {
                "implementation": "CPython",
                "version": "3.12.0",
                "executable": "python.exe",
                "environment": "system",
            },
        },
        "counts": {
            "tasks_planned": 1,
            "tasks_recorded": 1,
            "succeeded": 1 if status == "success" else 0,
            "skipped": 1 if status == "warning" else 0,
            "failed": 0 if status in {"success", "warning"} else 1,
            "warnings": 1 if status == "warning" else 0,
            "errors": 0 if status in {"success", "warning"} else 1,
        },
        "issue_groups": [],
        "artifacts": {
            "input": {"present": True, "bytes": 10, "sha256": "1" * 64},
            "runner_output": {"present": True, "bytes": 20, "sha256": "2" * 64},
        },
    }
    summary["integrity"] = {
        "algorithm": "sha256",
        "sha256": MODULE.hashlib.sha256(MODULE.canonical_json_bytes(summary)).hexdigest(),
    }
    path = project_root / "evidence" / "runs" / f"{run_id}.summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
        # Initialization configuration is part of the committed delivery baseline.
        (self.project_root / '.trellis/config.yaml').write_text('session_auto_commit: false\n', encoding='utf-8')
        subprocess.run(["git", "add", "AGENTS.md", ".trellis/config.yaml"], cwd=self.project_root, check=True)
        subprocess.run(["git", "commit", "-m", "test evidence"], cwd=self.project_root, check=True, capture_output=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit_file(self, relative_path: str, content: str, message: str) -> str:
        path = self.project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", relative_path], cwd=self.project_root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.project_root, check=True, capture_output=True)
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
        self.assertIn("accepted_baseline", project_schema["properties"])
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

    def test_portable_evidence_summary_is_validated_and_reported(self) -> None:
        commit = self.init_git()
        path = write_evidence_summary(self.project_root, commit)
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertTrue(checked["valid"])
        self.assertTrue(checked["delivery_ready"])
        self.assertTrue(checked["production_entrypoint"])
        status = MODULE.build_status(self.project_root)
        self.assertEqual(status["evidence_summary"]["run_id"], "portable-001")
        self.assertTrue(status["evidence_summary"]["delivery_ready"])

    def test_evidence_survives_record_commits_but_rejects_live_code_edits(self) -> None:
        commit = self.init_git()
        path = write_evidence_summary(self.project_root, commit)
        self.commit_file('evidence/runs/portable-001.summary.json', path.read_text(encoding='utf-8'), 'save evidence')
        self.commit_file('.trellis/workspace/reviewer/journal.md', 'accepted\n', 'save journal')
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertTrue(checked['delivery_ready'])
        self.assertFalse(checked['commit_matches_head'])
        runtime = self.project_root / 'core/中文文件.py'
        runtime.parent.mkdir()
        runtime.write_text('new code\n', encoding='utf-8')
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertTrue(checked['valid'])
        self.assertFalse(checked['delivery_ready'])
        self.assertIn('core/中文文件.py', checked['version_check']['delivery_paths'])

    def test_evidence_rejects_changed_then_reverted_code_history(self) -> None:
        commit = self.init_git()
        path = write_evidence_summary(self.project_root, commit)
        self.commit_file('AGENTS.md', 'changed\n', 'change instructions')
        self.commit_file('AGENTS.md', '# Agents\n', 'restore instructions')
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertFalse(checked['delivery_ready'])
        self.assertIn('AGENTS.md', checked['version_check']['delivery_paths'])

    def test_v2_delivery_clean_is_separate_from_raw_git_clean(self) -> None:
        commit = self.init_git()
        path = write_evidence_summary(self.project_root, commit, clean=False)
        summary = json.loads(path.read_text(encoding='utf-8'))
        self.assertFalse(MODULE.validate_evidence_summary(self.project_root, path)['delivery_ready'])
        summary['schema_version'] = 2
        summary['run']['delivery_tree_clean'] = True
        unsigned = {k: v for k, v in summary.items() if k != 'integrity'}
        summary['integrity']['sha256'] = MODULE.hashlib.sha256(MODULE.canonical_json_bytes(unsigned)).hexdigest()
        path.write_text(json.dumps(summary), encoding='utf-8')
        self.assertTrue(MODULE.validate_evidence_summary(self.project_root, path)['delivery_ready'])
        del summary['run']['delivery_tree_clean']
        path.write_text(json.dumps(summary), encoding='utf-8')
        self.assertFalse(MODULE.validate_evidence_summary(self.project_root, path)['valid'])

    def test_code_under_governance_directories_is_not_exempt(self) -> None:
        for path in ['.trellis/scripts/task.py', '.trellis/config.yaml', '.agents/skills/test/SKILL.md',
                     '.project-gates/plugin.py', 'evidence/runs/hook.py', '.gitignore']:
            self.assertFalse(MODULE.is_governance_path(path), path)

    def test_portable_evidence_rejects_tamper_sensitive_field_and_failure(self) -> None:
        commit = self.init_git()
        path = write_evidence_summary(self.project_root, commit)
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["counts"]["succeeded"] = 99
        path.write_text(json.dumps(summary), encoding="utf-8")
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertFalse(checked["valid"])
        self.assertIn("integrity hash mismatch", checked["errors"])

        path = write_evidence_summary(self.project_root, commit, run_id="sensitive")
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["runtime"]["payload"] = {"token": "secret"}
        unsigned = dict(summary)
        unsigned.pop("integrity")
        summary["integrity"]["sha256"] = MODULE.hashlib.sha256(MODULE.canonical_json_bytes(unsigned)).hexdigest()
        path.write_text(json.dumps(summary), encoding="utf-8")
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertFalse(checked["valid"])
        self.assertTrue(any("unexpected runtime fields" in item for item in checked["errors"]))

        path = write_evidence_summary(self.project_root, commit, status="pending_fix", run_id="failed")
        checked = MODULE.validate_evidence_summary(self.project_root, path)
        self.assertTrue(checked["valid"])
        self.assertFalse(checked["delivery_ready"])

    def test_portable_evidence_requires_clean_current_commit_and_run_bat(self) -> None:
        commit = self.init_git()
        dirty = MODULE.validate_evidence_summary(
            self.project_root,
            write_evidence_summary(self.project_root, commit, clean=False, run_id="dirty"),
        )
        self.assertFalse(dirty["delivery_ready"])
        direct = MODULE.validate_evidence_summary(
            self.project_root,
            write_evidence_summary(self.project_root, commit, entrypoint="runner.py", run_id="direct"),
        )
        self.assertFalse(direct["delivery_ready"])
        next_commit = self.commit_file("runtime.py", "print('changed')\n", "change runtime")
        self.assertNotEqual(commit, next_commit)
        stale = MODULE.validate_evidence_summary(
            self.project_root,
            write_evidence_summary(self.project_root, commit, run_id="stale"),
        )
        self.assertTrue(stale["valid"])
        self.assertFalse(stale["commit_matches_head"])
        self.assertFalse(stale["delivery_ready"])

    def test_legacy_project_without_baseline_remains_readable(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))

        status = MODULE.build_status(self.project_root)

        self.assertEqual(status["delivery_baseline"]["state"], "missing_accepted_baseline")
        self.assertIn("missing_accepted_baseline", {item["code"] for item in status["warnings"]})

    def test_gate_close_captures_exact_accepted_git_baseline(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))

        result = MODULE.close_gate(gate_args(self.project_root, baseline_commit=commit))

        baseline = result["read_back"]["accepted_baseline"]
        self.assertEqual(baseline["commit"], commit)
        self.assertEqual(baseline["gate"], "G0")
        self.assertEqual(baseline["event"], "gate-close")
        history = (self.project_root / ".project-gates" / "gate-history.md").read_text(encoding="utf-8")
        self.assertIn(f"- accepted_commit: {commit}", history)

    def test_status_classifies_governance_only_drift_without_user_review(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, baseline_commit=commit))

        status = MODULE.build_status(self.project_root)

        drift = status["delivery_baseline"]
        self.assertEqual(drift["state"], "governance_only_drift")
        self.assertFalse(drift["requires_user_review"])
        self.assertEqual(drift["delivery_paths"], [])
        self.assertTrue(any(path.startswith(".project-gates/") for path in drift["governance_paths"]))
        self.assertTrue(MODULE.is_governance_path(".trellis/tasks/archive/2026-09/中文项目/prd.md"))

    def test_status_flags_runtime_change_after_accepted_baseline(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, baseline_commit=commit))
        changed_commit = self.commit_file("run.bat", "@echo off\npython runner.py\n", "change runtime entrypoint")

        status = MODULE.build_status(self.project_root)

        drift = status["delivery_baseline"]
        self.assertEqual(drift["current_head"], changed_commit)
        self.assertEqual(drift["state"], "unaccepted_delivery_drift")
        self.assertTrue(drift["requires_user_review"])
        self.assertIn("run.bat", drift["delivery_paths"])
        self.assertEqual(MODULE.suggest_action(status)["recommended_action"], "review_unaccepted_drift")

    def test_status_flags_uncommitted_contract_change(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, baseline_commit=commit))
        contract = self.project_root / "docs" / "contract.md"
        contract.parent.mkdir(parents=True)
        contract.write_text("changed contract\n", encoding="utf-8")

        drift = MODULE.build_status(self.project_root)["delivery_baseline"]

        self.assertEqual(drift["state"], "unaccepted_delivery_drift")
        self.assertIn("docs/contract.md", drift["working_tree_paths"])
        self.assertIn("docs/contract.md", drift["delivery_paths"])

    def test_status_reports_missing_accepted_commit(self) -> None:
        self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["accepted_baseline"] = {
            "commit": "deadbeef",
            "gate": "G2",
            "event": "gate-close",
            "event_id": "missing-commit",
            "accepted_at": "2026-08-14T10:00:00+08:00",
        }
        project_path.write_text(json.dumps(project), encoding="utf-8")

        status = MODULE.build_status(self.project_root)

        self.assertEqual(status["delivery_baseline"]["state"], "accepted_baseline_missing")
        self.assertEqual(MODULE.suggest_action(status)["recommended_action"], "recover_accepted_baseline")

    def test_legacy_history_infers_baseline_and_detects_runtime_drift(self) -> None:
        accepted_commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update({"current_gate": "G5", "status": "operational"})
        project_path.write_text(json.dumps(project), encoding="utf-8")
        history_path = self.project_root / ".project-gates" / "gate-history.md"
        history_path.write_text(
            "# Project Gate History\n\n"
            "## 2026-08-14T10:00:00+08:00 - G5 gate-close\n\n"
            "- event: gate-close\n"
            "- event_id: legacy-g5\n"
            "- gate: G5\n"
            "- result: accepted\n"
            "- accepted_by: user\n"
            f"- evidence: runner:legacy.json, commit:{accepted_commit}\n",
            encoding="utf-8",
        )
        changed_commit = self.commit_file("run.bat", "@echo off\npython runner.py\n", "post acceptance runtime change")

        status = MODULE.build_status(self.project_root)

        drift = status["delivery_baseline"]
        self.assertEqual(drift["source"], "history_evidence")
        self.assertEqual(drift["accepted"]["commit"], accepted_commit)
        self.assertEqual(drift["current_head"], changed_commit)
        self.assertEqual(drift["state"], "unaccepted_delivery_drift")
        self.assertIn("run.bat", drift["delivery_paths"])
        self.assertIn("accepted_baseline_inferred", {item["code"] for item in status["warnings"]})

    def test_cli_status_emits_utf8_for_chinese_project_path(self) -> None:
        chinese_root = self.project_root / "中文项目"
        write_workspace(chinese_root)
        (chinese_root / "AGENTS.md").write_text("# 中文项目\n", encoding="utf-8")
        MODULE.bootstrap_collaboration(bootstrap_args(chinese_root, project_name="中文项目"))

        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "rpa_collab.py"), "--project-root", str(chinese_root), "status"],
            check=True,
            capture_output=True,
        )
        output = proc.stdout.decode("utf-8")
        self.assertIn("中文项目", output)
        self.assertEqual(json.loads(output)["project_gate"]["project_id"], "中文项目")

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

    def test_cli_returns_distinct_exit_code_for_partial_gate_commit(self) -> None:
        partial = {
            "ok": False,
            "partial_commit": True,
            "delivery_route_sync": {"status": "failed"},
        }
        with (
            mock.patch.object(CLI_MODULE.controller, "close_gate", return_value=partial),
            mock.patch.object(CLI_MODULE.controller, "print_json"),
        ):
            exit_code = CLI_MODULE.main(
                [
                    "--project-root",
                    str(self.project_root),
                    "gate-close",
                    "--accepted-gate",
                    "G0",
                    "--confirm-user-acceptance",
                ]
            )
        self.assertEqual(exit_code, 3)

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
        self.assertEqual(result["delivery_route_sync"]["status"], "not_applicable")

    def test_gate_close_syncs_required_task_delivery_review(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G2"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        write_task(
            self.project_root,
            meta={
                "delivery_route": {
                    "change_class": "major_change",
                    "entry": "G2",
                    "required_reviews": ["G2", "G3", "G4", "G5"],
                    "completed_reviews": [],
                    "project_revalidations": [],
                }
            },
        )

        result = MODULE.close_gate(
            gate_args(
                self.project_root,
                accepted_gate="G2",
                event_id="gate-close-g2-sync",
            )
        )

        task = json.loads(
            (self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["read_back"]["current_gate"], "G3")
        self.assertEqual(result["delivery_route_sync"]["status"], "updated")
        self.assertEqual(task["meta"]["delivery_route"]["completed_reviews"], ["G2"])
        self.assertNotIn("current_gate", task["meta"]["delivery_route"])

    def test_gate_close_keeps_legacy_task_without_creating_route(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G2"
        project_path.write_text(json.dumps(project), encoding="utf-8")

        result = MODULE.close_gate(
            gate_args(
                self.project_root,
                accepted_gate="G2",
                event_id="gate-close-g2-no-route",
            )
        )

        task = json.loads(
            (self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["delivery_route_sync"]["status"], "not_configured")
        self.assertNotIn("delivery_route", task["meta"])

    def test_gate_close_preflights_invalid_route_before_project_write(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G2"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        write_task(self.project_root, meta={"delivery_route": '{"entry":"G2"}'})

        with self.assertRaisesRegex(MODULE.CollabError, "JSON object"):
            MODULE.close_gate(
                gate_args(
                    self.project_root,
                    accepted_gate="G2",
                    event_id="gate-close-invalid-route",
                )
            )

        self.assertEqual(MODULE.read_project_gate(self.project_root)["current_gate"], "G2")
        history = (self.project_root / ".project-gates" / "gate-history.md").read_text(encoding="utf-8")
        self.assertNotIn("gate-close-invalid-route", history)

    def test_gate_close_reports_partial_commit_when_task_route_write_fails(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G2"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        write_task(
            self.project_root,
            meta={
                "delivery_route": {
                    "change_class": "major_change",
                    "entry": "G2",
                    "required_reviews": ["G2", "G3", "G4", "G5"],
                    "completed_reviews": [],
                    "project_revalidations": [],
                }
            },
        )
        original_write = MODULE.write_json_atomic

        def fail_task_write(path: Path, data: dict) -> None:
            if path.name == "task.json":
                raise OSError("simulated Task write failure")
            original_write(path, data)

        with mock.patch.object(MODULE, "write_json_atomic", side_effect=fail_task_write):
            result = MODULE.close_gate(
                gate_args(
                    self.project_root,
                    accepted_gate="G2",
                    event_id="gate-close-g2-partial",
                )
            )

        task = json.loads(
            (self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial_commit"])
        self.assertEqual(result["delivery_route_sync"]["status"], "failed")
        self.assertEqual(result["read_back"]["current_gate"], "G3")
        self.assertEqual(task["meta"]["delivery_route"]["completed_reviews"], [])
        self.assertIn("operation-recover", result["error"])
        self.assertIsNotNone(MODULE.transaction.inspect(self.project_root))

    def test_gate_close_rejects_second_close_of_same_gate(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root))
        with self.assertRaises(MODULE.CollabError):
            MODULE.close_gate(gate_args(self.project_root, event_id="second"))

    def test_gate_amendment_updates_baseline_without_rewinding_or_repeating_review(self) -> None:
        original_commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G0", event_id="close-g0", baseline_commit=original_commit))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G1", event_id="close-g1", baseline_commit=original_commit))
        MODULE.set_delivery_route(
            route_args(
                self.project_root,
                entry="G2",
                require_review=["G2", "G3", "G4", "G5"],
            )
        )
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G2", event_id="close-g2", baseline_commit=original_commit))
        amended_commit = self.commit_file("docs/contract.md", "contract v2\n", "amend accepted contract")

        result = MODULE.amend_gate(
            gate_args(
                self.project_root,
                gate="G2",
                event_id="amend-g2",
                reason="User accepted the corrected contract",
                baseline_commit=amended_commit,
            )
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["current_gate_unchanged"])
        self.assertEqual(result["read_back"]["current_gate"], "G3")
        self.assertEqual(result["previous_baseline"]["commit"], original_commit)
        self.assertEqual(result["accepted_baseline"]["commit"], amended_commit)
        self.assertEqual(result["accepted_baseline"]["event"], "gate-amendment")
        self.assertEqual(result["delivery_route_sync"]["status"], "already_completed")
        history = (self.project_root / ".project-gates" / "gate-history.md").read_text(encoding="utf-8")
        self.assertIn("- event: gate-amendment", history)
        self.assertIn(f"- previous_accepted_commit: {original_commit}", history)
        self.assertIn(f"- accepted_commit: {amended_commit}", history)
        with self.assertRaisesRegex(MODULE.CollabError, "event_id already exists"):
            MODULE.amend_gate(
                gate_args(
                    self.project_root,
                    gate="G2",
                    event_id="amend-g2",
                    reason="User accepted the corrected contract",
                    baseline_commit=amended_commit,
                )
            )

    def test_gate_amendment_repairs_late_task_route_review(self) -> None:
        original_commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G0", event_id="late-close-g0", baseline_commit=original_commit))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G1", event_id="late-close-g1", baseline_commit=original_commit))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G2", event_id="late-close-g2", baseline_commit=original_commit))
        MODULE.set_delivery_route(
            route_args(
                self.project_root,
                entry="G2",
                require_review=["G2", "G3", "G4", "G5"],
            )
        )
        amended_commit = self.commit_file("docs/late-contract.md", "contract v2\n", "amend late route contract")

        result = MODULE.amend_gate(
            gate_args(
                self.project_root,
                gate="G2",
                event_id="late-amend-g2",
                reason="User accepted the late route contract",
                baseline_commit=amended_commit,
            )
        )

        self.assertEqual(result["delivery_route_sync"]["status"], "updated")
        self.assertEqual(result["delivery_route_sync"]["completed_reviews"], ["G2"])
        self.assertEqual(result["read_back"]["current_gate"], "G3")

    def test_gate_amendment_requires_closed_gate_reason_confirmation_and_git(self) -> None:
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        with self.assertRaisesRegex(MODULE.CollabError, "confirm-user-acceptance"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G0", confirm_user_acceptance=False))
        with self.assertRaisesRegex(MODULE.CollabError, "non-empty reason"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G0", reason=""))
        with self.assertRaisesRegex(MODULE.CollabError, "initial gate-close"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G0"))

        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G0", event_id="close-before-no-git"))
        with self.assertRaisesRegex(MODULE.CollabError, "Cannot resolve Git commit"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G0", event_id="amend-without-git"))

    def test_gate_amendment_rejects_non_contract_gate_and_operational_project(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G0", event_id="close-g0", baseline_commit=commit))
        with self.assertRaisesRegex(MODULE.CollabError, "only for G0, G1, or G2"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G3", event_id="bad-g3", baseline_commit=commit))

        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update({"current_gate": "G5", "status": "active"})
        project_path.write_text(json.dumps(project), encoding="utf-8")
        MODULE.close_gate(gate_args(self.project_root, accepted_gate="G5", event_id="close-g5", baseline_commit=commit))
        with self.assertRaisesRegex(MODULE.CollabError, "before the first G5 close"):
            MODULE.amend_gate(gate_args(self.project_root, gate="G0", event_id="amend-after-g5", baseline_commit=commit))

    def test_cli_exposes_gate_amendment_and_baseline_commit(self) -> None:
        parsed = CLI_MODULE.build_parser().parse_args(
            [
                "--project-root",
                str(self.project_root),
                "gate-amendment",
                "--gate",
                "G2",
                "--baseline-commit",
                "abc1234",
                "--reason",
                "Corrected contract",
                "--evidence",
                "AGENTS.md",
                "--confirm-user-acceptance",
            ]
        )
        self.assertEqual(parsed.command, "gate-amendment")
        self.assertEqual(parsed.gate, "G2")
        self.assertEqual(parsed.baseline_commit, "abc1234")

    def test_cli_gate_amendment_appends_event_and_keeps_current_gate(self) -> None:
        original_commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        MODULE.close_gate(
            gate_args(
                self.project_root,
                accepted_gate="G0",
                event_id="cli-close-g0",
                baseline_commit=original_commit,
            )
        )
        amended_commit = self.commit_file("docs/scope.md", "scope v2\n", "amend scope")

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "rpa_collab.py"),
                "--project-root",
                str(self.project_root),
                "--task",
                "demo-delivery",
                "gate-amendment",
                "--gate",
                "G0",
                "--baseline-commit",
                amended_commit,
                "--reason",
                "User accepted corrected scope",
                "--evidence",
                "docs/scope.md",
                "--event-id",
                "cli-amend-g0",
                "--confirm-user-acceptance",
            ],
            check=True,
            capture_output=True,
        )
        result = json.loads(proc.stdout.decode("utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["event"]["event_id"], "cli-amend-g0")
        self.assertEqual(result["read_back"]["current_gate"], "G1")
        self.assertEqual(result["read_back"]["accepted_baseline"]["commit"], amended_commit)

    def test_g5_close_becomes_operational_and_revalidation_keeps_g5(self) -> None:
        commit = self.init_git()
        MODULE.bootstrap_collaboration(bootstrap_args(self.project_root))
        project_path = self.project_root / ".project-gates" / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["current_gate"] = "G5"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        close_result = MODULE.close_gate(
            gate_args(self.project_root, accepted_gate="G5", event_id="g5-close", baseline_commit=commit)
        )
        self.assertEqual(close_result["read_back"]["status"], "operational")
        MODULE.set_delivery_route(
            route_args(
                self.project_root,
                entry="G2",
                require_review=["G2", "G3", "G4", "G5"],
                project_revalidation=["G2"],
            )
        )
        revalidate = gate_args(
            self.project_root,
            gate="G2",
            reason="Major contract change accepted",
            event_id="g2-revalidation",
        )
        result = MODULE.revalidate_gate(revalidate)
        self.assertEqual(result["read_back"]["current_gate"], "G5")
        self.assertTrue(result["current_gate_unchanged"])
        self.assertEqual(result["delivery_route_sync"]["status"], "updated")
        self.assertEqual(result["read_back"]["accepted_baseline"]["event"], "gate-revalidation")
        self.assertEqual(result["read_back"]["accepted_baseline"]["commit"], commit)
        task = json.loads(
            (self.project_root / ".trellis" / "tasks" / "demo-delivery" / "task.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(task["meta"]["delivery_route"]["completed_reviews"], ["G2"])
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
