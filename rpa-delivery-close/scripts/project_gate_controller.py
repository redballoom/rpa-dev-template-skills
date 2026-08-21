#!/usr/bin/env python3
"""Project Gate controller and Trellis delivery guard.

The Project Gate Controller owns the project-level G0-G5 pointer and
append-only Gate events.
Trellis remains the only owner of engineering Task lifecycle and artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
NEXT_GATE = {"G0": "G1", "G1": "G2", "G2": "G3", "G3": "G4", "G4": "G5", "G5": "G5"}
PROJECT_STATUSES = ("active", "operational", "archived", "terminated")
DELIVERY_STATES = ("paused", "blocked", "in_review", "cancelled")
DEFAULT_TRELLIS_REGISTRY = "gh:redballoom/rpa-trellis-spec-templates"
DEFAULT_TRELLIS_TEMPLATE = "rpa-python-shadowbot"
SYSTEM_TASK_IDS = {"00-bootstrap-guidelines"}
PROJECT_GATE_DIR = ".project-gates"
LEGACY_PROJECT_GATE_DIR = ".hermes"


class CollabError(RuntimeError):
    """A user-actionable workflow or evidence error."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9._\-\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-._")
    if not text:
        raise CollabError("Project or task id cannot be empty")
    return text


def one_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollabError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CollabError(f"Expected JSON object in {path}")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def has_full_trellis_workspace(project_root: Path) -> bool:
    return (project_root / ".trellis" / "spec").is_dir()


def resolve_trellis_cmd(supplied: str | None = None) -> str | None:
    if supplied:
        return supplied
    env_cmd = os.environ.get("RPA_TRELLIS_CMD")
    if env_cmd:
        return env_cmd
    found = shutil.which("trellis") or shutil.which("trellis.cmd")
    if found:
        return found
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "npm" / "trellis.cmd"
        if candidate.exists():
            return str(candidate)
    return None


def run_trellis_init(project_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    cmd = resolve_trellis_cmd(args.trellis_cmd)
    if not cmd:
        raise CollabError("Cannot find Trellis CLI; pass --trellis-cmd or install Trellis in PATH")
    command = [cmd, "init", "--registry", args.trellis_registry, "--template", args.trellis_template]
    if args.trellis_codex:
        command.append("--codex")
    if args.dry_run:
        return {"ok": True, "dry_run": True, "command": command, "cwd": str(project_root)}
    proc = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    result = {
        "ok": proc.returncode == 0,
        "command": command,
        "cwd": str(project_root),
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    if proc.returncode != 0:
        raise CollabError(f"Trellis init failed: {json.dumps(result, ensure_ascii=False)}")
    if not has_full_trellis_workspace(project_root):
        raise CollabError("Trellis init completed but .trellis/spec was not found")
    return result


def ensure_trellis_safe_config(project_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Set the one safety-critical Trellis config without changing other keys."""

    config_path = project_root / ".trellis" / "config.yaml"
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = original.splitlines(keepends=True)
    output: list[str] = []
    found = False
    key_pattern = re.compile(r"^\s*(?:#\s*)?session_auto_commit\s*:")
    for line in lines:
        if key_pattern.match(line):
            if not found:
                output.append("session_auto_commit: false\n")
                found = True
            continue
        output.append(line)
    if not found:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += "\n"
        output.append("session_auto_commit: false\n")
    updated = "".join(output)
    changed = updated != original
    if changed and not dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(updated, encoding="utf-8")
    verified = re.search(r"(?m)^\s*session_auto_commit\s*:\s*false\s*(?:#.*)?$", updated) is not None
    if not verified:
        raise CollabError("Could not verify .trellis/config.yaml session_auto_commit: false")
    return {"path": str(config_path), "changed": changed, "verified": verified, "dry_run": dry_run}


def validate_project(project: dict[str, Any], path: Path) -> dict[str, Any]:
    allowed = {"schema_version", "project_id", "current_gate", "status", "updated_at"}
    extra = sorted(set(project) - allowed)
    if extra:
        raise CollabError(f"{path} contains unsupported fields: {extra}")
    if project.get("schema_version") != 1:
        raise CollabError(f"{path} must use schema_version 1")
    if not isinstance(project.get("project_id"), str) or not project["project_id"].strip():
        raise CollabError(f"{path} requires a non-empty project_id")
    if project.get("current_gate") not in GATES:
        raise CollabError(f"{path} has invalid current_gate: {project.get('current_gate')}")
    if project.get("status") not in PROJECT_STATUSES:
        raise CollabError(f"{path} has invalid status: {project.get('status')}")
    if not isinstance(project.get("updated_at"), str):
        raise CollabError(f"{path} requires updated_at")
    try:
        datetime.fromisoformat(project["updated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollabError(f"{path} has invalid updated_at: {project['updated_at']}") from exc
    return project


def project_gate_paths(project_root: Path) -> tuple[Path, Path]:
    gate_dir = project_root / PROJECT_GATE_DIR
    return gate_dir / "project.json", gate_dir / "gate-history.md"


def legacy_project_gate_paths(project_root: Path) -> tuple[Path, Path]:
    legacy_dir = project_root / LEGACY_PROJECT_GATE_DIR
    return legacy_dir / "project.json", legacy_dir / "gate-history.md"


def legacy_project_gate_records(project_root: Path) -> list[str]:
    return [str(path) for path in legacy_project_gate_paths(project_root) if path.exists()]


def read_project_gate(project_root: Path, *, required: bool = True) -> dict[str, Any] | None:
    project_path, _ = project_gate_paths(project_root)
    if not project_path.exists():
        if required:
            legacy = legacy_project_gate_records(project_root)
            if legacy:
                raise CollabError(
                    "Legacy project Gate state exists under .hermes/. Run migration-preview "
                    "and migrate-project-gates before continuing; .hermes/ is reserved for Hermes Agent."
                )
            raise CollabError("Project Gate tracking is not bootstrapped; run rpa_collab bootstrap first")
        return None
    return validate_project(read_json(project_path), project_path)


def ensure_project_gate(project_root: Path, project_id: str, initial_gate: str = "G0", *, dry_run: bool = False) -> dict[str, Any]:
    if initial_gate not in ("G0", "G1"):
        raise CollabError("Bootstrap initial_gate must be G0 or G1")
    project_path, history_path = project_gate_paths(project_root)
    if project_path.exists():
        project = validate_project(read_json(project_path), project_path)
        expected_id = slugify(project_id)
        if project["project_id"] != expected_id:
            raise CollabError(
                f"Project Gate project_id is {project['project_id']}; bootstrap requested {expected_id}"
            )
        return {"created": False, "project": project, "project_path": str(project_path)}
    legacy = legacy_project_gate_records(project_root)
    if legacy:
        raise CollabError(
            "Legacy project Gate state exists under .hermes/. Refusing to create a second Gate "
            "snapshot; run migration-preview and migrate-project-gates first."
        )
    project = {
        "schema_version": 1,
        "project_id": slugify(project_id),
        "current_gate": initial_gate,
        "status": "active",
        "updated_at": now_iso(),
    }
    if not dry_run:
        write_json_atomic(project_path, project)
        if not history_path.exists():
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("# Project Gate History\n\n", encoding="utf-8")
    return {"created": True, "project": project, "project_path": str(project_path), "dry_run": dry_run}


def is_archive_path(task_file: Path, tasks_root: Path) -> bool:
    try:
        return "archive" in task_file.relative_to(tasks_root).parts
    except ValueError:
        return False


def find_task_files(project_root: Path) -> list[Path]:
    root = project_root / ".trellis" / "tasks"
    return sorted(root.rglob("task.json")) if root.is_dir() else []


def task_id(task_file: Path, data: dict[str, Any]) -> str:
    return str(data.get("id") or task_file.parent.name)


def is_system_task(task_file: Path, data: dict[str, Any]) -> bool:
    return task_id(task_file, data) in SYSTEM_TASK_IDS or task_id(task_file, data).startswith("00-bootstrap-")


def active_tasks(project_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    tasks_root = project_root / ".trellis" / "tasks"
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in find_task_files(project_root):
        data = read_json(path)
        if is_archive_path(path, tasks_root) or is_system_task(path, data):
            continue
        if data.get("status") in ("planning", "in_progress"):
            found.append((path, data))
    return found


def match_task(project_root: Path, task_input: str | None) -> tuple[Path, dict[str, Any]]:
    files = find_task_files(project_root)
    tasks_root = project_root / ".trellis" / "tasks"
    if task_input:
        direct = Path(task_input)
        candidates = [direct] if direct.is_absolute() else [project_root / direct, tasks_root / direct]
        for candidate in candidates:
            candidate_file = candidate if candidate.name == "task.json" else candidate / "task.json"
            if candidate_file.is_file():
                return candidate_file, read_json(candidate_file)
        matches = [(path, read_json(path)) for path in files if task_id(path, read_json(path)) == task_input or path.parent.name == task_input]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise CollabError(f"Task not found: {task_input}")
        raise CollabError(f"Task identifier is ambiguous: {task_input}")
    active = active_tasks(project_root)
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        raise CollabError("Multiple active engineering Tasks found; pass --task explicitly")
    non_system = [(path, read_json(path)) for path in files if not is_system_task(path, read_json(path))]
    if len(non_system) == 1:
        return non_system[0]
    raise CollabError("No engineering Task found; pass --task explicitly")


def create_task(project_root: Path, task_id_value: str, task_name: str, *, dry_run: bool = False) -> tuple[Path, dict[str, Any]]:
    if active_tasks(project_root):
        raise CollabError("An active engineering Task already exists; pass --task to attach to it")
    slug = slugify(task_id_value)
    task_dir = project_root / ".trellis" / "tasks" / slug
    task_file = task_dir / "task.json"
    if task_file.exists():
        return task_file, read_json(task_file)
    task_script = project_root / ".trellis" / "scripts" / "task.py"
    if task_script.is_file() and not dry_run:
        before = set(find_task_files(project_root))
        command = [
            sys.executable,
            str(task_script),
            "create",
            task_name,
            "--slug",
            slug,
            "--description",
            "Project delivery Task managed by Trellis; project Gates are managed by the Project Gate Controller.",
            "--no-start",
        ]
        proc = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            raise CollabError(f"Trellis task.py create failed: {proc.stderr.strip() or proc.stdout.strip()}")
        created = [path for path in find_task_files(project_root) if path not in before]
        if len(created) != 1:
            raise CollabError(f"Trellis task.py create produced {len(created)} new Tasks; expected one")
        return created[0], read_json(created[0])
    data = {
        "id": slug,
        "name": task_name,
        "title": task_name,
        "description": "Project delivery Task managed by Trellis; project Gates are managed by the Project Gate Controller.",
        "status": "planning",
        "dev_type": None,
        "scope": None,
        "package": None,
        "priority": "P2",
        "creator": None,
        "assignee": None,
        "createdAt": datetime.now().astimezone().date().isoformat(),
        "completedAt": None,
        "branch": None,
        "base_branch": None,
        "worktree_path": None,
        "commit": None,
        "pr_url": None,
        "subtasks": [],
        "children": [],
        "parent": None,
        "relatedFiles": [],
        "notes": "",
        "meta": {},
    }
    if not dry_run:
        write_json_atomic(task_file, data)
    return task_file, data


def latest_runner(project_root: Path) -> dict[str, Any] | None:
    candidates = sorted(project_root.glob("runner_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            data = read_json(candidate)
        except CollabError:
            continue
        return {"path": str(candidate), "status": data.get("status"), "run_id": data.get("run_id") or candidate.stem.removeprefix("runner_")}
    return None


def run_git(project_root: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip()


def git_info(project_root: Path) -> dict[str, Any]:
    code, head = run_git(project_root, ["log", "-1", "--oneline"])
    if code != 0:
        return {"available": False}
    _, dirty = run_git(project_root, ["status", "--short"])
    return {"available": True, "head": head, "dirty": bool(dirty)}


def legacy_gate_records(project_root: Path) -> list[str]:
    records: list[str] = []
    for path in find_task_files(project_root):
        data = read_json(path)
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        progress = meta.get("progress") if isinstance(meta, dict) else None
        if isinstance(progress, dict) and progress.get("current_gate") in GATES:
            records.append(str(path))
        if path.parent.joinpath("progress.md").exists():
            records.append(str(path.parent / "progress.md"))
    return sorted(set(records))


def build_status(project_root: Path, task_input: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    project = read_project_gate(project_root, required=False)
    selected: dict[str, Any] | None = None
    selected_path: Path | None = None
    selection_error: str | None = None
    try:
        selected_path, selected_data = match_task(project_root, task_input)
        selected_meta = selected_data.get("meta") if isinstance(selected_data.get("meta"), dict) else {}
        selected = {"path": str(selected_path), "id": task_id(selected_path, selected_data), "status": selected_data.get("status"), "delivery_state": selected_meta.get("delivery_state")}
    except CollabError as exc:
        selection_error = str(exc)
    tasks = []
    warnings: list[dict[str, str]] = []
    for path in find_task_files(project_root):
        data = read_json(path)
        if is_system_task(path, data):
            continue
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        delivery_state = meta.get("delivery_state")
        tasks.append({"path": str(path), "id": task_id(path, data), "status": data.get("status"), "archived": is_archive_path(path, project_root / ".trellis" / "tasks"), "delivery_state": delivery_state})
        if delivery_state is not None and delivery_state not in DELIVERY_STATES:
            warnings.append({"code": "invalid_delivery_state", "message": f"Task {task_id(path, data)} has invalid delivery_state: {delivery_state}"})
    legacy_project_gates = legacy_project_gate_records(project_root)
    if legacy_project_gates:
        warnings.append(
            {
                "code": "legacy_project_gate_directory",
                "message": "Legacy project Gate files under .hermes/ require explicit migration to .project-gates/",
            }
        )
    if project is None:
        warnings.append({"code": "missing_project_gate", "message": "Project Gate tracking is not bootstrapped"})
    if len(active_tasks(project_root)) > 1:
        warnings.append({"code": "multiple_active_tasks", "message": "More than one active engineering Task exists"})
    legacy = legacy_gate_records(project_root)
    if legacy:
        warnings.append({"code": "legacy_gate_records", "message": "Legacy Task-local Gate records require migration"})
    config = project_root / ".trellis" / "config.yaml"
    if config.exists() and not re.search(r"(?m)^\s*session_auto_commit\s*:\s*false\s*(?:#.*)?$", config.read_text(encoding="utf-8")):
        warnings.append({"code": "unsafe_session_auto_commit", "message": "Trellis config is not explicitly session_auto_commit: false"})
    if selection_error and tasks:
        warnings.append({"code": "task_selection", "message": selection_error})
    return {
        "ok": True,
        "project_root": str(project_root),
        "project_gate": project,
        "selected_task": selected,
        "tasks": tasks,
        "legacy_records": legacy,
        "legacy_project_gate_records": legacy_project_gates,
        "warnings": warnings,
        "runner": latest_runner(project_root),
        "git": git_info(project_root),
    }


def suggest_action(status: dict[str, Any]) -> dict[str, Any]:
    codes = {item["code"] for item in status.get("warnings", [])}
    if "legacy_project_gate_directory" in codes and status.get("project_gate"):
        action, reason = "resolve_project_gate_conflict", "Both current and legacy Gate records exist; compare them before removing the legacy files."
    elif "legacy_project_gate_directory" in codes:
        action, reason = "migrate_project_gates", "Move legacy Gate files out of the Hermes Agent project namespace before continuing."
    elif "missing_project_gate" in codes:
        action, reason = "bootstrap", "Create project Gate state before recording a Gate decision."
    elif "unsafe_session_auto_commit" in codes:
        action, reason = "configure_trellis", "Write and read back session_auto_commit: false before archive or journal operations."
    elif "legacy_gate_records" in codes:
        action, reason = "migration_preview", "Review legacy Task-local Gate records and migrate them into the Project Gate Controller after user awareness."
    elif "multiple_active_tasks" in codes:
        action, reason = "inspect_tasks", "Resolve the active engineering Task policy before continuing."
    elif status.get("project_gate", {}).get("current_gate") == "G5":
        action, reason = "continue_task_or_revalidate", "Keep the project at G5; use a Task for maintenance or Gate revalidation for major change."
    else:
        action, reason = "continue_current_gate", "Continue the selected engineering Task and close the current project Gate only after user acceptance."
    return {"ok": True, "recommended_action": action, "reason": reason, "current_gate": (status.get("project_gate") or {}).get("current_gate")}


def evidence_path(project_root: Path, reference: str) -> Path | None:
    if reference.startswith(("issue:", "pr:", "http://", "https://", "#")):
        return None
    if reference.startswith("commit:"):
        code, _ = run_git(project_root, ["cat-file", "-e", f"{reference.removeprefix('commit:')}^{{commit}}"])
        if code != 0:
            raise CollabError(f"Evidence commit does not exist: {reference}")
        return None
    raw = reference.removeprefix("runner:").removeprefix("run:")
    candidate = project_root / raw
    if candidate.exists():
        return candidate
    if raw.startswith("runner_"):
        match = next(iter(project_root.glob(raw if raw.endswith(".json") else raw + ".json")), None)
        if match:
            return match
    raise CollabError(f"Evidence path does not exist: {reference}")


def require_evidence(project_root: Path, refs: list[str]) -> list[str]:
    if not refs:
        raise CollabError("At least one evidence reference is required")
    for ref in refs:
        evidence_path(project_root, ref)
    return refs


def event_id(event_type: str, gate: str, timestamp: str, args: argparse.Namespace) -> str:
    supplied = getattr(args, "event_id", None)
    if supplied:
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", supplied):
            raise CollabError("event_id may contain only letters, numbers, dot, underscore, colon, and hyphen")
        return supplied
    raw = f"{event_type}|{gate}|{timestamp}|{getattr(args, 'reason', '')}|{','.join(getattr(args, 'evidence', []) or [])}"
    return f"{event_type}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def history_has_event(history: str, stable_id: str) -> bool:
    return f"- event_id: {stable_id}" in history


def history_has_gate_close(project_root: Path, gate: str) -> bool:
    _, history_path = project_gate_paths(project_root)
    if not history_path.exists():
        return False
    for section in history_path.read_text(encoding="utf-8").split("\n## "):
        if "- event: gate-close" in section and f"- gate: {gate}" in section:
            return True
    return False


def append_gate_event(project_root: Path, *, event_type: str, gate: str, accepted_by: str, timestamp: str, stable_id: str, task: str | None, evidence: list[str], reason: str, dry_run: bool = False) -> dict[str, Any]:
    _, history_path = project_gate_paths(project_root)
    existing = history_path.read_text(encoding="utf-8") if history_path.exists() else "# Project Gate History\n\n"
    if history_has_event(existing, stable_id):
        return {"appended": False, "duplicate": True, "event_id": stable_id, "history_path": str(history_path)}
    lines = [f"## {one_line(timestamp)} - {gate} {event_type}", "", f"- event: {event_type}", f"- event_id: {stable_id}", f"- gate: {gate}", "- result: accepted", f"- accepted_by: {one_line(accepted_by)}"]
    if reason:
        lines.append(f"- reason: {one_line(reason)}")
    if task:
        lines.append(f"- tasks: {one_line(task)}")
    if evidence:
        lines.append(f"- evidence: {', '.join(one_line(item) for item in evidence)}")
    lines.extend(["", ""])
    if not dry_run:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(existing.rstrip() + "\n\n" + "\n".join(lines), encoding="utf-8")
    return {"appended": True, "duplicate": False, "event_id": stable_id, "history_path": str(history_path), "dry_run": dry_run}


def bootstrap_collaboration(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    trellis_result = None
    if not has_full_trellis_workspace(project_root):
        if args.init_trellis:
            trellis_result = run_trellis_init(project_root, args)
        elif not args.allow_minimal:
            raise CollabError("Full Trellis workspace is missing; run trellis init first or pass --init-trellis")
    safe_config = ensure_trellis_safe_config(project_root, dry_run=args.dry_run) if (project_root / ".trellis").exists() or args.init_trellis else None
    project_gate = ensure_project_gate(project_root, args.project_name, args.initial_gate, dry_run=args.dry_run)
    created_task = False
    if args.task:
        task_file, task_data = match_task(project_root, args.task)
    else:
        try:
            task_file, task_data = match_task(project_root, None)
        except CollabError:
            task_file, task_data = create_task(
                project_root,
                args.task_id or args.project_name,
                args.task_name or args.project_name,
                dry_run=args.dry_run,
            )
            created_task = True
    return {"ok": True, "created_task": created_task, "task_file": str(task_file), "task_id": task_id(task_file, task_data), "trellis_workspace": "full" if has_full_trellis_workspace(project_root) else "minimal", "trellis_init": trellis_result, "trellis_config": safe_config, "project_gate": project_gate, "status": build_status(project_root, str(task_file.parent)) if not args.dry_run else None}


def close_gate(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_user_acceptance:
        raise CollabError("Gate close requires --confirm-user-acceptance after the user explicitly accepts the result")
    project_root = Path(args.project_root).resolve()
    project_path, _ = project_gate_paths(project_root)
    project = read_project_gate(project_root)
    if project["current_gate"] != args.accepted_gate:
        raise CollabError(f"Project Gate current_gate is {project['current_gate']}; cannot close {args.accepted_gate}")
    if args.accepted_gate == "G5" and (
        project["status"] != "active" or history_has_gate_close(project_root, "G5")
    ):
        raise CollabError("G5 was already closed; use gate-revalidate for later work")
    refs = require_evidence(project_root, args.evidence)
    timestamp = args.timestamp or now_iso()
    stable_id = event_id("gate-close", args.accepted_gate, timestamp, args)
    task_file, task_data = match_task(project_root, args.task) if args.task or find_task_files(project_root) else (None, {})
    result_gate = NEXT_GATE[args.accepted_gate]
    event = append_gate_event(project_root, event_type="gate-close", gate=args.accepted_gate, accepted_by="user", timestamp=timestamp, stable_id=stable_id, task=task_id(task_file, task_data) if task_file else None, evidence=refs, reason=args.reason, dry_run=args.dry_run)
    project["current_gate"] = result_gate
    if args.accepted_gate == "G5":
        project["status"] = "operational"
    project["updated_at"] = timestamp
    if not args.dry_run:
        write_json_atomic(project_path, project)
    return {"ok": True, "event": event, "project": project, "read_back": read_project_gate(project_root), "dry_run": args.dry_run}


def revalidate_gate(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_user_acceptance:
        raise CollabError("Gate revalidation requires --confirm-user-acceptance")
    project_root = Path(args.project_root).resolve()
    project = read_project_gate(project_root)
    if project["current_gate"] != "G5" or project["status"] != "operational":
        raise CollabError("Gate revalidation is available only after the first G5 close")
    refs = require_evidence(project_root, args.evidence)
    timestamp = args.timestamp or now_iso()
    stable_id = event_id("gate-revalidation", args.gate, timestamp, args)
    task_file, task_data = match_task(project_root, args.task) if args.task or find_task_files(project_root) else (None, {})
    event = append_gate_event(project_root, event_type="gate-revalidation", gate=args.gate, accepted_by="user", timestamp=timestamp, stable_id=stable_id, task=task_id(task_file, task_data) if task_file else None, evidence=refs, reason=args.reason, dry_run=args.dry_run)
    return {"ok": True, "event": event, "project": project, "current_gate_unchanged": True, "read_back": read_project_gate(project_root), "dry_run": args.dry_run}


def archive_check(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    task_file, task = match_task(project_root, args.task)
    meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
    raw_requirements = meta.get("delivery_requirements")
    requirements = raw_requirements if isinstance(raw_requirements, dict) else {}
    archive = meta.get("archive_evidence") if isinstance(meta.get("archive_evidence"), dict) else {}
    ac = archive.get("acceptance_criteria") or task.get("acceptance_criteria") or meta.get("acceptance_criteria")
    checks = archive.get("technical_checks") or task.get("technical_checks") or meta.get("technical_checks")
    evidence = archive.get("evidence_refs") or task.get("evidence_refs") or meta.get("evidence_refs") or []
    missing: list[str] = []
    required_requirement_keys = (
        "require_pr",
        "require_runner",
        "require_user_acceptance",
    )
    if not isinstance(raw_requirements, dict):
        missing.append("delivery_requirements")
    else:
        for key in required_requirement_keys:
            if not isinstance(raw_requirements.get(key), bool):
                missing.append(f"delivery_requirements.{key}")
    try:
        read_project_gate(project_root)
    except CollabError:
        missing.append("project_gate_state")
    config_path = project_root / ".trellis" / "config.yaml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if not re.search(r"(?m)^\s*session_auto_commit\s*:\s*false\s*(?:#.*)?$", config_text):
        missing.append("session_auto_commit_false")
    if task.get("status") == "completed" or is_archive_path(task_file, project_root / ".trellis" / "tasks"):
        missing.append("task_already_archived")
    delivery_state = meta.get("delivery_state")
    if delivery_state in {"paused", "blocked", "cancelled"}:
        missing.append(f"delivery_state:{delivery_state}")

    def passed_items(items: Any, field: str) -> bool:
        if not isinstance(items, list) or not items:
            return False
        valid_results = {"passed", "accepted", "met", "complete", "completed"}
        for index, item in enumerate(items):
            if not isinstance(item, dict) or str(item.get("result", "")).lower() not in valid_results:
                return False
            refs = item.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                return False
            for ref in refs:
                try:
                    evidence_path(project_root, str(ref))
                except CollabError:
                    missing.append(f"{field}[{index}].evidence:{ref}")
        return True

    if not passed_items(ac, "acceptance_criteria"):
        missing.append("acceptance_criteria")
    if not passed_items(checks, "technical_checks"):
        missing.append("technical_checks")
    final_summary = archive.get("final_summary") or meta.get("final_summary")
    if not isinstance(final_summary, str) or not final_summary.strip():
        missing.append("final_summary")
    commit = archive.get("commit") or task.get("commit") or meta.get("commit")
    if not commit:
        missing.append("commit")
    elif isinstance(commit, str):
        try:
            evidence_path(project_root, commit if commit.startswith("commit:") else f"commit:{commit}")
        except CollabError:
            missing.append("commit")
    if requirements.get("require_pr") and not (archive.get("pr_url") or task.get("pr_url") or meta.get("pr_url")):
        missing.append("pr_url")
    if requirements.get("require_runner"):
        runner_refs = archive.get("runner_refs") or task.get("runner_refs") or meta.get("runner_refs") or []
        runner_ok = False
        for ref in runner_refs if isinstance(runner_refs, list) else []:
            try:
                path = evidence_path(project_root, str(ref))
                runner = read_json(path) if path else {}
                runner_ok = runner_ok or runner.get("status") in {"success", "warning"}
            except CollabError:
                continue
        latest = latest_runner(project_root)
        runner_ok = runner_ok or bool(latest and latest.get("status") in {"success", "warning"})
        if not runner_ok:
            missing.append("runner_evidence")
    if requirements.get("require_user_acceptance") and not (args.user_accepted or archive.get("user_acceptance") is True):
        missing.append("user_acceptance")
    for ref in evidence if isinstance(evidence, list) else []:
        try:
            evidence_path(project_root, str(ref))
        except CollabError:
            missing.append(f"evidence:{ref}")
    missing = sorted(set(missing))
    return {"ok": not missing, "ready": not missing, "task_file": str(task_file), "task_id": task_id(task_file, task), "missing": missing, "requirements": requirements, "archive_evidence": archive}


def migration_preview(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    records = legacy_gate_records(project_root)
    legacy_project_records = legacy_project_gate_records(project_root)
    project_gate = read_project_gate(project_root, required=False)
    actions: list[str] = []
    if legacy_project_records and project_gate:
        actions.append(
            "Both .project-gates/ and legacy .hermes/ Gate records exist. Compare them and resolve the conflict; "
            "migrate-project-gates will not merge two states."
        )
    elif legacy_project_records:
        actions.append(
            "Run migrate-project-gates with explicit confirmation to move only the legacy Gate files "
            "from .hermes/ to .project-gates/."
        )
    if records:
        actions.append(
            "After user awareness, recover verified Task-local Gate facts into the Project Gate Controller; "
            "do not dual-write."
        )
    if not actions:
        actions.append("No legacy project Gate records were found.")
    return {
        "ok": True,
        "write_performed": False,
        "legacy_records": records,
        "legacy_project_gate_records": legacy_project_records,
        "project_gate": project_gate,
        "actions": actions,
    }


def migrate_project_gates(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_migration:
        raise CollabError("Project Gate directory migration requires --confirm-migration")

    project_root = Path(args.project_root).resolve()
    legacy_project_path, legacy_history_path = legacy_project_gate_paths(project_root)
    project_path, history_path = project_gate_paths(project_root)
    gate_dir = project_path.parent

    if project_path.exists() or history_path.exists():
        raise CollabError(
            ".project-gates/ already contains Gate state; refusing to merge it with legacy .hermes/ files"
        )
    if gate_dir.exists() and any(gate_dir.iterdir()):
        raise CollabError(".project-gates/ contains unknown files; refusing to write migration output")
    if not legacy_project_path.exists():
        raise CollabError("No legacy .hermes/project.json Gate snapshot was found")

    project = validate_project(read_json(legacy_project_path), legacy_project_path)
    history = (
        legacy_history_path.read_text(encoding="utf-8")
        if legacy_history_path.exists()
        else "# Project Gate History\n\n"
    )
    timestamp = getattr(args, "timestamp", None) or now_iso()
    migration_event = "\n".join(
        [
            f"## {timestamp} - controller-storage-migration",
            "",
            "- event: controller-storage-migration",
            "- from: .hermes/",
            "- to: .project-gates/",
            "- result: completed",
            "- reason: avoid collision with the Hermes Agent project namespace",
            "",
        ]
    )

    if args.dry_run:
        return {
            "ok": True,
            "write_performed": False,
            "dry_run": True,
            "source_records": legacy_project_gate_records(project_root),
            "destination": str(project_path.parent),
            "project": project,
        }

    project_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_json_atomic(project_path, project)
        history_path.write_text(history.rstrip() + "\n\n" + migration_event, encoding="utf-8")
        read_project_gate(project_root)
    except Exception:
        if project_path.exists():
            project_path.unlink()
        if history_path.exists():
            history_path.unlink()
        try:
            project_path.parent.rmdir()
        except OSError:
            pass
        raise

    cleanup_errors: list[str] = []
    for legacy_path in (legacy_project_path, legacy_history_path):
        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except OSError as exc:
                cleanup_errors.append(f"{legacy_path}: {exc}")
    try:
        legacy_project_path.parent.rmdir()
    except OSError:
        pass

    if cleanup_errors:
        raise CollabError(
            "Project Gate state was written to .project-gates/, but legacy Gate files could not be removed: "
            + "; ".join(cleanup_errors)
        )

    return {
        "ok": True,
        "write_performed": True,
        "source": LEGACY_PROJECT_GATE_DIR,
        "destination": PROJECT_GATE_DIR,
        "project": read_project_gate(project_root),
        "history_path": str(history_path),
        "legacy_directory_preserved": legacy_project_path.parent.exists(),
        "cleanup_errors": cleanup_errors,
    }


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
