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
from delivery_version import delivery_version, is_record_path
import gate_transaction as transaction


GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
NEXT_GATE = {"G0": "G1", "G1": "G2", "G2": "G3", "G3": "G4", "G4": "G5", "G5": "G5"}
PROJECT_STATUSES = ("active", "operational", "archived", "terminated")
DELIVERY_STATES = ("paused", "blocked", "in_review", "cancelled")
DELIVERY_REVIEWS = ("G2", "G3", "G4", "G5")
AMENDABLE_GATES = ("G0", "G1", "G2")
BASELINE_EVENT_TYPES = ("gate-close", "gate-revalidation", "gate-amendment")
DEFAULT_TRELLIS_REGISTRY = "gh:redballoom/rpa-trellis-spec-templates"
DEFAULT_TRELLIS_TEMPLATE = "rpa-python-shadowbot"
SYSTEM_TASK_IDS = {"00-bootstrap-guidelines"}
PROJECT_GATE_DIR = ".project-gates"
LEGACY_PROJECT_GATE_DIR = ".hermes"
GOVERNANCE_PATH_PREFIXES = (
    ".project-gates/",
    ".trellis/",
    ".agents/",
    ".codex/",
)
GOVERNANCE_PATHS = {
    ".gitignore",
    "AGENTS.md",
}
EVIDENCE_SUMMARY_TOP_LEVEL = {
    "schema_version", "run", "runtime", "counts", "issue_groups", "artifacts", "integrity",
}
EVIDENCE_SUMMARY_FIELDS = {
    "run": {"run_id", "status", "started_at", "finished_at", "commit", "working_tree_clean"},
    "runtime": {"entrypoint", "interpreter"},
    "interpreter": {"implementation", "version", "executable", "environment"},
    "counts": {"tasks_planned", "tasks_recorded", "succeeded", "skipped", "failed", "warnings", "errors"},
    "issue_group": {"kind", "code", "category", "retryable", "count"},
    "artifacts": {"input", "runner_output"},
    "artifact": {"present", "bytes", "sha256"},
    "integrity": {"algorithm", "sha256"},
}
EVIDENCE_SUMMARY_STATUSES = {
    "success", "warning", "retryable_error", "pending_fix", "failed", "locked", "fatal",
}


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
    transaction.atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


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


def validate_accepted_baseline(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CollabError(f"{path} accepted_baseline must be a JSON object")
    allowed = {"commit", "gate", "event", "event_id", "accepted_at"}
    extra = sorted(set(value) - allowed)
    if extra:
        raise CollabError(f"{path} accepted_baseline contains unsupported fields: {extra}")
    commit = value.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit):
        raise CollabError(f"{path} accepted_baseline.commit must be a Git commit hash")
    if value.get("gate") not in GATES:
        raise CollabError(f"{path} accepted_baseline.gate must be one of G0-G5")
    if value.get("event") not in BASELINE_EVENT_TYPES:
        raise CollabError(f"{path} accepted_baseline.event is invalid")
    event_id_value = value.get("event_id")
    if not isinstance(event_id_value, str) or not event_id_value.strip():
        raise CollabError(f"{path} accepted_baseline.event_id must be non-empty")
    accepted_at = value.get("accepted_at")
    if not isinstance(accepted_at, str):
        raise CollabError(f"{path} accepted_baseline.accepted_at is required")
    try:
        datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollabError(f"{path} accepted_baseline.accepted_at is invalid: {accepted_at}") from exc
    return value


def validate_project(project: dict[str, Any], path: Path) -> dict[str, Any]:
    allowed = {"schema_version", "project_id", "current_gate", "status", "updated_at", "accepted_baseline"}
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
    if "accepted_baseline" in project:
        validate_accepted_baseline(project["accepted_baseline"], path)
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


def ordered_reviews(values: list[str] | tuple[str, ...]) -> list[str]:
    selected = set(values)
    return [gate for gate in DELIVERY_REVIEWS if gate in selected]


def validate_delivery_route(route: Any, project: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise CollabError("delivery_route must be a JSON object, not a Trellis set-meta string")
    allowed = {
        "change_class",
        "entry",
        "required_reviews",
        "completed_reviews",
        "project_revalidations",
    }
    unknown = sorted(set(route) - allowed)
    if unknown:
        raise CollabError(f"delivery_route has unsupported fields: {', '.join(unknown)}")
    change_class = route.get("change_class")
    if not isinstance(change_class, str) or not change_class.strip() or "\n" in change_class:
        raise CollabError("delivery_route.change_class must be a non-empty one-line string")

    def reviews(field: str, *, required: bool = False) -> list[str]:
        value = route.get(field)
        if not isinstance(value, list) or (required and not value):
            qualifier = "a non-empty array" if required else "an array"
            raise CollabError(f"delivery_route.{field} must be {qualifier}")
        if any(item not in DELIVERY_REVIEWS for item in value):
            raise CollabError(f"delivery_route.{field} may contain only G2, G3, G4, and G5")
        if len(value) != len(set(value)):
            raise CollabError(f"delivery_route.{field} must not contain duplicates")
        return ordered_reviews(value)

    required_reviews = reviews("required_reviews", required=True)
    completed_reviews = reviews("completed_reviews")
    project_revalidations = reviews("project_revalidations")
    entry = route.get("entry")
    if entry not in DELIVERY_REVIEWS:
        raise CollabError("delivery_route.entry must be one of G2, G3, G4, or G5")
    if entry != required_reviews[0]:
        raise CollabError("delivery_route.entry must equal the first required review")
    if not set(completed_reviews).issubset(required_reviews):
        raise CollabError("delivery_route.completed_reviews must be a subset of required_reviews")
    if not set(project_revalidations).issubset(required_reviews):
        raise CollabError("delivery_route.project_revalidations must be a subset of required_reviews")
    if project_revalidations and (not project or project.get("current_gate") != "G5" or project.get("status") != "operational"):
        raise CollabError("project_revalidations are available only for an operational G5 project")
    return {
        "change_class": change_class.strip(),
        "entry": entry,
        "required_reviews": required_reviews,
        "completed_reviews": completed_reviews,
        "project_revalidations": project_revalidations,
    }


def check_delivery_route(project_root: Path, task_input: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    task_file, task = match_task(project_root, task_input)
    meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
    route = meta.get("delivery_route")
    if route is None:
        return {
            "ok": True,
            "present": False,
            "task_file": str(task_file),
            "task_id": task_id(task_file, task),
            "delivery_route": None,
            "legacy_compatible": True,
        }
    project = read_project_gate(project_root, required=False)
    normalized = validate_delivery_route(route, project)
    return {
        "ok": True,
        "present": True,
        "task_file": str(task_file),
        "task_id": task_id(task_file, task),
        "delivery_route": normalized,
        "project_gate_unchanged": True,
    }


@transaction.guarded
def set_delivery_route(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_delivery_route:
        raise CollabError("Refusing to write delivery_route without --confirm-delivery-route")
    project_root = Path(args.project_root).resolve()
    project = read_project_gate(project_root)
    task_file, task = match_task(project_root, args.task)
    if is_archive_path(task_file, project_root / ".trellis" / "tasks"):
        raise CollabError("Refusing to change delivery_route on an archived Task")
    route = validate_delivery_route(
        {
            "change_class": args.change_class,
            "entry": args.entry,
            "required_reviews": args.require_review,
            "completed_reviews": args.complete_review,
            "project_revalidations": args.project_revalidation,
        },
        project,
    )
    meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
    before = meta.get("delivery_route")
    if not args.dry_run:
        task["meta"] = {**meta, "delivery_route": route}
        write_json_atomic(task_file, task)
        read_back = check_delivery_route(project_root, task_id(task_file, task))["delivery_route"]
        if read_back != route:
            raise CollabError("delivery_route read-back verification failed")
    else:
        read_back = route
    return {
        "ok": True,
        "task_file": str(task_file),
        "task_id": task_id(task_file, task),
        "before": before,
        "delivery_route": route,
        "read_back": read_back,
        "project_gate_unchanged": True,
        "dry_run": args.dry_run,
    }


def sync_delivery_route_review(
    project_root: Path,
    task_file: Path | None,
    task: dict[str, Any],
    review: str,
    project: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Record one accepted review in an existing Task-owned delivery route."""

    if task_file is None or review not in DELIVERY_REVIEWS:
        return {"status": "not_applicable", "review": review, "dry_run": dry_run}
    if is_archive_path(task_file, project_root / ".trellis" / "tasks"):
        raise CollabError("Refusing to synchronize delivery_route on an archived Task")

    meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
    raw_route = meta.get("delivery_route")
    base = {
        "review": review,
        "task_file": str(task_file),
        "task_id": task_id(task_file, task),
        "dry_run": dry_run,
    }
    if raw_route is None:
        return {**base, "status": "not_configured"}

    route = validate_delivery_route(raw_route, project)
    completed = route["completed_reviews"]
    if review not in route["required_reviews"]:
        return {**base, "status": "not_required", "completed_reviews": completed}
    if review in completed:
        return {**base, "status": "already_completed", "completed_reviews": completed}

    updated_route = {
        **route,
        "completed_reviews": ordered_reviews([*completed, review]),
    }
    if dry_run:
        return {
            **base,
            "status": "would_update",
            "before": completed,
            "completed_reviews": updated_route["completed_reviews"],
        }

    updated_task = {**task, "meta": {**meta, "delivery_route": updated_route}}
    write_json_atomic(task_file, updated_task)
    read_back_task = read_json(task_file)
    read_back_meta = read_back_task.get("meta") if isinstance(read_back_task.get("meta"), dict) else {}
    read_back = validate_delivery_route(read_back_meta.get("delivery_route"), project)
    if read_back != updated_route:
        raise CollabError("delivery_route accepted-review read-back verification failed")
    return {
        **base,
        "status": "updated",
        "before": completed,
        "completed_reviews": read_back["completed_reviews"],
    }


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
    try:
        proc = subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout.strip()


def resolve_git_commit(project_root: Path, reference: str | None = None, *, required: bool = False) -> str | None:
    target = reference or "HEAD"
    code, commit = run_git(project_root, ["rev-parse", "--verify", f"{target}^{{commit}}"])
    if code == 0 and commit:
        return commit.splitlines()[-1].strip().lower()
    if reference or required:
        raise CollabError(f"Cannot resolve Git commit: {target}")
    return None


def is_evidence_summary_path(path: Path) -> bool:
    normalized = path.as_posix().lower()
    return normalized.endswith(".summary.json") and "/evidence/runs/" in "/" + normalized.lstrip("/")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _check_summary_fields(errors: list[str], value: Any, kind: str) -> None:
    if not isinstance(value, dict):
        errors.append(f"{kind} must be an object")
        return
    unexpected = sorted(set(value) - EVIDENCE_SUMMARY_FIELDS[kind])
    missing = sorted(EVIDENCE_SUMMARY_FIELDS[kind] - set(value))
    if unexpected:
        errors.append(f"unexpected {kind} fields: {', '.join(unexpected)}")
    if missing:
        errors.append(f"missing {kind} fields: {', '.join(missing)}")


def validate_evidence_summary(project_root: Path, path: Path) -> dict[str, Any]:
    """Validate a portable summary without depending on the runtime template package."""
    project_root = project_root.resolve()
    path = path.resolve()
    try:
        summary = read_json(path)
    except CollabError as exc:
        return {"path": str(path), "valid": False, "delivery_ready": False, "errors": [str(exc)]}

    errors: list[str] = []
    unexpected = sorted(set(summary) - EVIDENCE_SUMMARY_TOP_LEVEL)
    missing = sorted(EVIDENCE_SUMMARY_TOP_LEVEL - set(summary))
    if unexpected:
        errors.append(f"unexpected top-level fields: {', '.join(unexpected)}")
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if summary.get("schema_version") not in (1, 2):
        errors.append("unsupported schema_version")

    run = summary.get("run")
    runtime = summary.get("runtime")
    counts = summary.get("counts")
    groups = summary.get("issue_groups")
    artifacts = summary.get("artifacts")
    integrity = summary.get("integrity")
    if isinstance(run, dict) and summary.get("schema_version") == 2:
        _check_summary_fields(errors, {k: v for k, v in run.items() if k != "delivery_tree_clean"}, "run")
        if not isinstance(run.get("delivery_tree_clean"), bool):
            errors.append("delivery_tree_clean must be boolean for schema 2")
    else:
        _check_summary_fields(errors, run, "run")
    _check_summary_fields(errors, runtime, "runtime")
    _check_summary_fields(errors, runtime.get("interpreter") if isinstance(runtime, dict) else None, "interpreter")
    _check_summary_fields(errors, counts, "counts")
    _check_summary_fields(errors, artifacts, "artifacts")
    _check_summary_fields(errors, integrity, "integrity")
    if isinstance(artifacts, dict):
        _check_summary_fields(errors, artifacts.get("input"), "artifact")
        _check_summary_fields(errors, artifacts.get("runner_output"), "artifact")
    if not isinstance(groups, list):
        errors.append("issue_groups must be an array")
    else:
        for item in groups:
            _check_summary_fields(errors, item, "issue_group")

    if isinstance(run, dict):
        if not isinstance(run.get("run_id"), str) or not run.get("run_id"):
            errors.append("run_id must be a non-empty string")
        if not isinstance(run.get("working_tree_clean"), bool):
            errors.append("working_tree_clean must be boolean")
        for field in ("started_at", "finished_at"):
            if not isinstance(run.get(field), str) or not run.get(field):
                errors.append(f"{field} must be a non-empty string")
    if isinstance(runtime, dict):
        if runtime.get("entrypoint") not in {"run.bat", "runner.py"}:
            errors.append("entrypoint must be run.bat or runner.py")
        interpreter_value = runtime.get("interpreter")
        if isinstance(interpreter_value, dict):
            for field in ("implementation", "version", "executable"):
                if not isinstance(interpreter_value.get(field), str) or not interpreter_value.get(field):
                    errors.append(f"interpreter.{field} must be a non-empty string")
            if interpreter_value.get("environment") not in {"project_venv", "virtualenv", "system"}:
                errors.append("invalid interpreter.environment")
    if isinstance(counts, dict):
        for field, value in counts.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"counts.{field} must be a non-negative integer")
    if isinstance(groups, list):
        for index, item in enumerate(groups):
            if not isinstance(item, dict):
                continue
            if item.get("kind") not in {"warning", "error"}:
                errors.append(f"issue_groups[{index}].kind is invalid")
            if not isinstance(item.get("retryable"), bool):
                errors.append(f"issue_groups[{index}].retryable must be boolean")
            if not isinstance(item.get("count"), int) or isinstance(item.get("count"), bool) or item.get("count", 0) < 1:
                errors.append(f"issue_groups[{index}].count must be a positive integer")
    if isinstance(artifacts, dict):
        for label in ("input", "runner_output"):
            artifact = artifacts.get(label)
            if not isinstance(artifact, dict):
                continue
            if not isinstance(artifact.get("present"), bool):
                errors.append(f"artifacts.{label}.present must be boolean")
            if not isinstance(artifact.get("bytes"), int) or isinstance(artifact.get("bytes"), bool) or artifact.get("bytes", -1) < 0:
                errors.append(f"artifacts.{label}.bytes must be a non-negative integer")
            digest = str(artifact.get("sha256") or "")
            if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
                errors.append(f"artifacts.{label}.sha256 is invalid")

    expected_hash = integrity.get("sha256", "") if isinstance(integrity, dict) else ""
    unsigned = dict(summary)
    unsigned.pop("integrity", None)
    actual_hash = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256" or not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash)):
        errors.append("invalid integrity metadata")
    elif expected_hash != actual_hash:
        errors.append("integrity hash mismatch")

    run = run if isinstance(run, dict) else {}
    runtime = runtime if isinstance(runtime, dict) else {}
    status = run.get("status")
    commit = str(run.get("commit") or "").lower()
    if status not in EVIDENCE_SUMMARY_STATUSES:
        errors.append("invalid run status")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append("run commit must be an exact 40-character SHA")
    commit_exists = False
    commit_matches_head = False
    if re.fullmatch(r"[0-9a-f]{40}", commit):
        code, _ = run_git(project_root, ["cat-file", "-e", f"{commit}^{{commit}}"])
        commit_exists = code == 0
        try:
            commit_matches_head = commit_exists and resolve_git_commit(project_root, required=True) == commit
        except CollabError:
            commit_matches_head = False

    interpreter = runtime.get("interpreter") if isinstance(runtime.get("interpreter"), dict) else {}
    production_entrypoint = runtime.get("entrypoint") == "run.bat"
    accepted_status = status in {"success", "warning"}
    working_tree_clean = run.get("working_tree_clean") is True
    run_delivery_clean = (run.get("delivery_tree_clean") is True
                          if summary.get("schema_version") == 2 else working_tree_clean)
    version = delivery_version(project_root, commit)
    valid = not errors
    delivery_ready = all(
        [valid, accepted_status, run_delivery_clean, commit_exists, production_entrypoint,
         version["ok"], version["baseline_compatible"], version["delivery_tree_clean"]]
    )
    return {
        "path": str(path),
        "valid": valid,
        "delivery_ready": delivery_ready,
        "errors": errors,
        "run_id": run.get("run_id"),
        "status": status,
        "commit": commit,
        "working_tree_clean": working_tree_clean,
        "run_delivery_tree_clean": run_delivery_clean,
        "current_delivery_tree_clean": version["delivery_tree_clean"],
        "version_check": version,
        "commit_exists": commit_exists,
        "commit_matches_head": commit_matches_head,
        "entrypoint": runtime.get("entrypoint"),
        "production_entrypoint": production_entrypoint,
        "interpreter": interpreter,
        "counts": counts if isinstance(counts, dict) else {},
        "integrity_sha256": actual_hash,
    }


def latest_evidence_summary(project_root: Path) -> dict[str, Any] | None:
    evidence_dir = project_root / "evidence" / "runs"
    candidates = sorted(evidence_dir.glob("*.summary.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return validate_evidence_summary(project_root, candidates[0]) if candidates else None


def git_paths(project_root: Path, args: list[str]) -> list[str]:
    code, output = run_git(project_root, ["-c", "core.quotepath=false", *args])
    if code != 0 or not output:
        return []
    return sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()})


def working_tree_paths(project_root: Path) -> list[str]:
    paths = set(git_paths(project_root, ["diff", "--name-only"]))
    paths.update(git_paths(project_root, ["diff", "--cached", "--name-only"]))
    paths.update(git_paths(project_root, ["ls-files", "--others", "--exclude-standard"]))
    return sorted(paths)


def git_info(project_root: Path) -> dict[str, Any]:
    code, head = run_git(project_root, ["log", "-1", "--oneline"])
    if code != 0:
        return {"available": False}
    head_sha = resolve_git_commit(project_root, required=True)
    dirty_paths = working_tree_paths(project_root)
    return {"available": True, "head": head, "head_sha": head_sha, "dirty": bool(dirty_paths), "dirty_paths": dirty_paths}


def is_governance_path(value: str) -> bool:
    path = value.strip().replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return is_record_path(path)


def infer_accepted_baseline_from_history(project_root: Path) -> dict[str, Any] | None:
    _, history_path = project_gate_paths(project_root)
    if not history_path.exists():
        return None
    sections = re.split(r"(?m)^## ", history_path.read_text(encoding="utf-8"))
    for raw_section in reversed(sections[1:]):
        section = "## " + raw_section
        if "- result: accepted" not in section:
            continue
        header = re.search(r"^## (\S+) - (G[0-5])", section)
        event = re.search(r"(?m)^- event: (gate-close|gate-revalidation|gate-amendment)\s*$", section)
        stable_id = re.search(r"(?m)^- event_id: (\S+)\s*$", section)
        if not header or not event or not stable_id:
            continue
        accepted_commits = re.findall(r"(?m)^- accepted_commit: ([0-9a-fA-F]{7,64})\s*$", section)
        evidence_commits = re.findall(r"commit:([0-9a-fA-F]{7,64})", section)
        for reference in reversed(accepted_commits or evidence_commits):
            try:
                commit = resolve_git_commit(project_root, reference)
            except CollabError:
                continue
            if commit:
                return {
                    "commit": commit,
                    "gate": header.group(2),
                    "event": event.group(1),
                    "event_id": stable_id.group(1),
                    "accepted_at": header.group(1),
                }
    return None


def build_delivery_baseline(project_root: Path, project: dict[str, Any] | None, git: dict[str, Any]) -> dict[str, Any]:
    recorded = project.get("accepted_baseline") if project else None
    inferred = infer_accepted_baseline_from_history(project_root) if project and recorded is None and git.get("available") else None
    accepted = recorded or inferred
    base: dict[str, Any] = {
        "accepted": accepted,
        "source": "project_snapshot" if recorded else ("history_evidence" if inferred else "unavailable"),
        "current_head": git.get("head_sha") if git.get("available") else None,
        "state": "unavailable",
        "head_relation": "unknown",
        "committed_paths": [],
        "working_tree_paths": git.get("dirty_paths", []) if git.get("available") else [],
        "governance_paths": [],
        "delivery_paths": [],
        "requires_user_review": False,
        "next_owner": "agent",
    }
    if project is None:
        base.update({"state": "missing_project_gate", "next_owner": "user_or_agent"})
        return base
    if accepted is None:
        base.update({"state": "missing_accepted_baseline", "next_owner": "user"})
        return base
    if not git.get("available"):
        base.update({"state": "git_unavailable", "next_owner": "environment_owner"})
        return base

    accepted_commit = str(accepted["commit"])
    code, _ = run_git(project_root, ["cat-file", "-e", f"{accepted_commit}^{{commit}}"])
    if code != 0:
        base.update({"state": "accepted_baseline_missing", "next_owner": "agent"})
        return base

    current_head = str(git["head_sha"])
    ancestor_code, _ = run_git(project_root, ["merge-base", "--is-ancestor", accepted_commit, current_head])
    head_relation = "same" if accepted_commit == current_head else ("descendant" if ancestor_code == 0 else "diverged")
    version = delivery_version(project_root, accepted_commit)
    if not version['ok'] and head_relation != 'diverged':
        base.update({'state': 'git_unavailable', 'requires_user_review': True,
                     'next_owner': 'environment_owner'})
        return base
    committed = version['committed_paths']
    working = version['working_paths']
    changed = sorted(set(committed) | set(working))
    governance = [path for path in changed if is_governance_path(path)]
    delivery = [path for path in changed if not is_governance_path(path)]

    if head_relation == "diverged":
        state = "history_diverged"
        requires_review = True
        next_owner = "user_and_agent"
    elif delivery:
        state = "unaccepted_delivery_drift"
        requires_review = True
        next_owner = "agent"
    elif changed or accepted_commit != current_head:
        state = "governance_only_drift"
        requires_review = False
        next_owner = "agent"
    else:
        state = "aligned"
        requires_review = False
        next_owner = "none"

    base.update(
        {
            "state": state,
            "head_relation": head_relation,
            "committed_paths": committed,
            "working_tree_paths": working,
            "governance_paths": governance,
            "delivery_paths": delivery,
            "requires_user_review": requires_review,
            "next_owner": next_owner,
        }
    )
    return base


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
    pending = transaction.inspect(project_root)
    if pending:
        return {"ok": False, "project_root": str(project_root), "project_gate": None,
                "pending_operation": pending, "warnings": [{"code": "pending_operation",
                "message": "Gate records may be partially written; inspect and recover before relying on them"}]}
    project = read_project_gate(project_root, required=False)
    selected: dict[str, Any] | None = None
    selected_path: Path | None = None
    selection_error: str | None = None
    try:
        selected_path, selected_data = match_task(project_root, task_input)
        selected_meta = selected_data.get("meta") if isinstance(selected_data.get("meta"), dict) else {}
        selected = {"path": str(selected_path), "id": task_id(selected_path, selected_data), "status": selected_data.get("status"), "delivery_state": selected_meta.get("delivery_state")}
        if "delivery_route" in selected_meta:
            selected["delivery_route"] = selected_meta["delivery_route"]
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
        task_summary = {"path": str(path), "id": task_id(path, data), "status": data.get("status"), "archived": is_archive_path(path, project_root / ".trellis" / "tasks"), "delivery_state": delivery_state}
        if "delivery_route" in meta:
            task_summary["delivery_route"] = meta["delivery_route"]
        tasks.append(task_summary)
        if delivery_state is not None and delivery_state not in DELIVERY_STATES:
            warnings.append({"code": "invalid_delivery_state", "message": f"Task {task_id(path, data)} has invalid delivery_state: {delivery_state}"})
        if "delivery_route" in meta:
            try:
                validate_delivery_route(meta["delivery_route"], project)
            except CollabError as exc:
                warnings.append({"code": "invalid_delivery_route", "message": f"Task {task_id(path, data)}: {exc}"})
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
    git = git_info(project_root)
    delivery_baseline = build_delivery_baseline(project_root, project, git)
    baseline_state = delivery_baseline["state"]
    if delivery_baseline["source"] == "history_evidence":
        warnings.append(
            {
                "code": "accepted_baseline_inferred",
                "message": "Accepted baseline was inferred from legacy Gate history evidence; persist it at the next accepted Gate event",
            }
        )
    baseline_messages = {
        "missing_accepted_baseline": "No accepted Git baseline is recorded; the next accepted Gate event must capture one",
        "git_unavailable": "An accepted baseline exists but Git is unavailable in this project",
        "accepted_baseline_missing": "The recorded accepted baseline commit does not exist in this Git repository",
        "history_diverged": "Current HEAD does not descend from the accepted baseline; review the Git history before delivery",
        "unaccepted_delivery_drift": "Runtime, contract, documentation, or business files changed after the accepted baseline",
        "governance_only_drift": "Only recognized governance files changed after the accepted baseline",
    }
    if baseline_state in baseline_messages:
        warnings.append({"code": baseline_state, "message": baseline_messages[baseline_state]})
    evidence_summary = latest_evidence_summary(project_root)
    if evidence_summary and not evidence_summary["valid"]:
        warnings.append({"code": "invalid_evidence_summary", "message": "; ".join(evidence_summary["errors"])})
    elif evidence_summary and not evidence_summary["delivery_ready"]:
        warnings.append(
            {
                "code": "evidence_summary_not_delivery_ready",
                "message": "Latest portable evidence is not a successful clean-commit run through run.bat at current HEAD",
            }
        )
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
        "evidence_summary": evidence_summary,
        "git": git,
        "delivery_baseline": delivery_baseline,
    }


def suggest_action(status: dict[str, Any]) -> dict[str, Any]:
    codes = {item["code"] for item in status.get("warnings", [])}
    if "pending_operation" in codes:
        return {"ok": False, "recommended_action": "operation_recover",
                "reason": "Inspect pending operation, then explicitly recover; do not repeat the Gate event",
                "current_gate": None}
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
    elif "invalid_delivery_route" in codes:
        action, reason = "check_delivery_route", "Correct the Issue-scoped Task route without changing the project Gate."
    elif "multiple_active_tasks" in codes:
        action, reason = "inspect_tasks", "Resolve the active engineering Task policy before continuing."
    elif "history_diverged" in codes:
        action, reason = "review_git_history", "Current HEAD diverged from the accepted baseline; inspect history before any Gate or archive action."
    elif "unaccepted_delivery_drift" in codes:
        action, reason = "review_unaccepted_drift", "Delivery-impacting files changed after the accepted baseline; validate the change before reporting delivery."
    elif "accepted_baseline_missing" in codes:
        action, reason = "recover_accepted_baseline", "Recover or explicitly replace the missing accepted commit before relying on delivery status."
    elif "missing_accepted_baseline" in codes and status.get("project_gate", {}).get("current_gate") != "G0":
        action, reason = "record_accepted_baseline", "The project advanced without a Git acceptance baseline; capture one at the next explicit Gate acceptance."
    elif "invalid_evidence_summary" in codes or "evidence_summary_not_delivery_ready" in codes:
        action, reason = "rerun_production_entrypoint", "Regenerate portable evidence from a clean current commit through run.bat before delivery."
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
        path = evidence_path(project_root, ref)
        if path and is_evidence_summary_path(path):
            validation = validate_evidence_summary(project_root, path)
            if not validation["valid"]:
                raise CollabError(f"Portable evidence summary is invalid: {ref}: {'; '.join(validation['errors'])}")
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
    return f"- event_id: {stable_id}" in history.splitlines()


def history_has_gate_close(project_root: Path, gate: str) -> bool:
    _, history_path = project_gate_paths(project_root)
    if not history_path.exists():
        return False
    for section in history_path.read_text(encoding="utf-8").split("\n## "):
        if "- event: gate-close" in section and f"- gate: {gate}" in section:
            return True
    return False


def make_accepted_baseline(
    project_root: Path,
    *,
    gate: str,
    event_type: str,
    stable_id: str,
    timestamp: str,
    baseline_commit: str | None = None,
    required: bool = False,
) -> dict[str, Any] | None:
    commit = resolve_git_commit(project_root, baseline_commit, required=required)
    if commit is None:
        return None
    return {
        "commit": commit,
        "gate": gate,
        "event": event_type,
        "event_id": stable_id,
        "accepted_at": timestamp,
    }


def append_gate_event(
    project_root: Path,
    *,
    event_type: str,
    gate: str,
    accepted_by: str,
    timestamp: str,
    stable_id: str,
    task: str | None,
    evidence: list[str],
    reason: str,
    previous_baseline: dict[str, Any] | None = None,
    accepted_baseline: dict[str, Any] | None = None,
    dry_run: bool = False,
    writes: dict[Path, str] | None = None,
) -> dict[str, Any]:
    _, history_path = project_gate_paths(project_root)
    existing = history_path.read_text(encoding="utf-8") if history_path.exists() else "# Project Gate History\n\n"
    if history_has_event(existing, stable_id):
        raise CollabError(f"Gate event_id already exists: {stable_id}")
    lines = [f"## {one_line(timestamp)} - {gate} {event_type}", "", f"- event: {event_type}", f"- event_id: {stable_id}", f"- gate: {gate}", "- result: accepted", f"- accepted_by: {one_line(accepted_by)}"]
    if reason:
        lines.append(f"- reason: {one_line(reason)}")
    if task:
        lines.append(f"- tasks: {one_line(task)}")
    if evidence:
        lines.append(f"- evidence: {', '.join(one_line(item) for item in evidence)}")
    if previous_baseline:
        lines.append(f"- previous_accepted_commit: {one_line(previous_baseline['commit'])}")
    elif event_type == "gate-amendment":
        lines.append("- previous_accepted_commit: unavailable")
    if accepted_baseline:
        lines.append(f"- accepted_commit: {one_line(accepted_baseline['commit'])}")
    lines.extend(["", ""])
    if not dry_run:
        rendered = existing.rstrip() + "\n\n" + "\n".join(lines)
        if writes is not None:
            writes[history_path] = rendered
        else:
            transaction.atomic_text(history_path, rendered)
    return {"appended": True, "duplicate": False, "event_id": stable_id, "history_path": str(history_path), "dry_run": dry_run}


def commit_gate_update(project_root, writes, project_path, project, task_file,
                       task_data, route_preflight, stable_id):
    writes[project_path] = json.dumps(project, ensure_ascii=False, indent=2) + "\n"
    if route_preflight["status"] == "would_update":
        meta = task_data["meta"]
        route = {**meta["delivery_route"], "completed_reviews": route_preflight["completed_reviews"]}
        updated = {**task_data, "meta": {**meta, "delivery_route": route}}
        writes[task_file] = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    transaction.prepare(project_root, stable_id, writes)
    try:
        transaction.apply_pending(project_root, write_json_atomic)
    except (transaction.TransactionError, CollabError, OSError) as exc:
        return {**route_preflight, "status": "failed", "dry_run": False, "error": str(exc)}
    return {**route_preflight, "dry_run": False,
            "status": "updated" if route_preflight["status"] == "would_update" else route_preflight["status"]}


def recover_operation(args):
    if not args.dry_run and not args.confirm_recovery:
        raise CollabError("operation-recover requires --confirm-recovery after inspecting the pending operation")
    with transaction.project_lock(args.project_root):
        return transaction.apply_pending(args.project_root, write_json_atomic, dry_run=args.dry_run)


@transaction.guarded
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


@transaction.guarded
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
    route_preflight = sync_delivery_route_review(
        project_root,
        task_file,
        task_data,
        args.accepted_gate,
        project,
        dry_run=True,
    )
    result_gate = NEXT_GATE[args.accepted_gate]
    previous_baseline = project.get("accepted_baseline")
    accepted_baseline = make_accepted_baseline(
        project_root,
        gate=args.accepted_gate,
        event_type="gate-close",
        stable_id=stable_id,
        timestamp=timestamp,
        baseline_commit=getattr(args, "baseline_commit", None),
    )
    writes: dict[Path, str] = {}
    event = append_gate_event(
        project_root,
        event_type="gate-close",
        gate=args.accepted_gate,
        accepted_by="user",
        timestamp=timestamp,
        stable_id=stable_id,
        task=task_id(task_file, task_data) if task_file else None,
        evidence=refs,
        reason=args.reason,
        previous_baseline=previous_baseline,
        accepted_baseline=accepted_baseline,
        dry_run=args.dry_run,
        writes=writes,
    )
    project["current_gate"] = result_gate
    if args.accepted_gate == "G5":
        project["status"] = "operational"
    if accepted_baseline:
        project["accepted_baseline"] = accepted_baseline
    project["updated_at"] = timestamp
    route_sync = route_preflight
    if not args.dry_run:
        route_sync = commit_gate_update(
            project_root, writes, project_path, project, task_file, task_data,
            route_preflight, stable_id,
        )
    synchronized = route_sync["status"] != "failed"
    if not synchronized:
        event["appended"] = history_has_event(
            transaction.text_at(project_gate_paths(project_root)[1]) or "", stable_id
        )
    result = {
        "ok": synchronized,
        "event": event,
        "project": project,
        "read_back": read_project_gate(project_root),
        "delivery_route_sync": route_sync,
        "dry_run": args.dry_run,
    }
    if not synchronized:
        result["partial_commit"] = True
        result["error"] = (
            "Gate operation is incomplete. Inspect status and run operation-recover; do not repeat the Gate event."
        )
    return result


@transaction.guarded
def revalidate_gate(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_user_acceptance:
        raise CollabError("Gate revalidation requires --confirm-user-acceptance")
    project_root = Path(args.project_root).resolve()
    project_path, _ = project_gate_paths(project_root)
    project = read_project_gate(project_root)
    if project["current_gate"] != "G5" or project["status"] != "operational":
        raise CollabError("Gate revalidation is available only after the first G5 close")
    refs = require_evidence(project_root, args.evidence)
    timestamp = args.timestamp or now_iso()
    stable_id = event_id("gate-revalidation", args.gate, timestamp, args)
    task_file, task_data = match_task(project_root, args.task) if args.task or find_task_files(project_root) else (None, {})
    route_preflight = sync_delivery_route_review(
        project_root,
        task_file,
        task_data,
        args.gate,
        project,
        dry_run=True,
    )
    previous_baseline = project.get("accepted_baseline")
    accepted_baseline = make_accepted_baseline(
        project_root,
        gate=args.gate,
        event_type="gate-revalidation",
        stable_id=stable_id,
        timestamp=timestamp,
        baseline_commit=getattr(args, "baseline_commit", None),
    )
    writes: dict[Path, str] = {}
    event = append_gate_event(
        project_root,
        event_type="gate-revalidation",
        gate=args.gate,
        accepted_by="user",
        timestamp=timestamp,
        stable_id=stable_id,
        task=task_id(task_file, task_data) if task_file else None,
        evidence=refs,
        reason=args.reason,
        previous_baseline=previous_baseline,
        accepted_baseline=accepted_baseline,
        dry_run=args.dry_run,
        writes=writes,
    )
    if accepted_baseline:
        project["accepted_baseline"] = accepted_baseline
    project["updated_at"] = timestamp
    route_sync = route_preflight
    if not args.dry_run:
        route_sync = commit_gate_update(
            project_root, writes, project_path, project, task_file, task_data,
            route_preflight, stable_id,
        )
    synchronized = route_sync["status"] != "failed"
    if not synchronized:
        event["appended"] = history_has_event(
            transaction.text_at(project_gate_paths(project_root)[1]) or "", stable_id
        )
    result = {
        "ok": synchronized,
        "event": event,
        "project": project,
        "current_gate_unchanged": True,
        "read_back": read_project_gate(project_root),
        "delivery_route_sync": route_sync,
        "dry_run": args.dry_run,
    }
    if not synchronized:
        result["partial_commit"] = True
        result["error"] = (
            "Gate operation is incomplete. Inspect status and run operation-recover; do not repeat the Gate event."
        )
    return result


@transaction.guarded
def amend_gate(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_user_acceptance:
        raise CollabError("Gate amendment requires --confirm-user-acceptance")
    if args.gate not in AMENDABLE_GATES:
        raise CollabError("Gate amendment is available only for G0, G1, or G2")
    if not str(args.reason).strip():
        raise CollabError("Gate amendment requires a non-empty reason")

    project_root = Path(args.project_root).resolve()
    project_path, _ = project_gate_paths(project_root)
    project = read_project_gate(project_root)
    if project["status"] != "active" or history_has_gate_close(project_root, "G5"):
        raise CollabError("Gate amendment is available only before the first G5 close; use gate-revalidate afterward")
    if not history_has_gate_close(project_root, args.gate):
        raise CollabError(f"Cannot amend {args.gate} before its initial gate-close event")
    if GATES.index(project["current_gate"]) <= GATES.index(args.gate):
        raise CollabError(f"Cannot amend {args.gate} while current_gate is {project['current_gate']}")

    refs = require_evidence(project_root, args.evidence)
    timestamp = args.timestamp or now_iso()
    stable_id = event_id("gate-amendment", args.gate, timestamp, args)
    task_file, task_data = match_task(project_root, args.task) if args.task or find_task_files(project_root) else (None, {})
    route_preflight = sync_delivery_route_review(
        project_root,
        task_file,
        task_data,
        args.gate,
        project,
        dry_run=True,
    )
    previous_baseline = project.get("accepted_baseline")
    accepted_baseline = make_accepted_baseline(
        project_root,
        gate=args.gate,
        event_type="gate-amendment",
        stable_id=stable_id,
        timestamp=timestamp,
        baseline_commit=getattr(args, "baseline_commit", None),
        required=True,
    )
    writes: dict[Path, str] = {}
    event = append_gate_event(
        project_root,
        event_type="gate-amendment",
        gate=args.gate,
        accepted_by="user",
        timestamp=timestamp,
        stable_id=stable_id,
        task=task_id(task_file, task_data) if task_file else None,
        evidence=refs,
        reason=args.reason,
        previous_baseline=previous_baseline,
        accepted_baseline=accepted_baseline,
        dry_run=args.dry_run,
        writes=writes,
    )
    if event["duplicate"]:
        raise CollabError(f"Gate amendment event_id already exists: {stable_id}")
    project["accepted_baseline"] = accepted_baseline
    project["updated_at"] = timestamp
    route_sync = route_preflight
    if not args.dry_run:
        route_sync = commit_gate_update(
            project_root, writes, project_path, project, task_file, task_data,
            route_preflight, stable_id,
        )
    synchronized = route_sync["status"] != "failed"
    if not synchronized:
        event["appended"] = history_has_event(
            transaction.text_at(project_gate_paths(project_root)[1]) or "", stable_id
        )
    result = {
        "ok": synchronized,
        "event": event,
        "project": project,
        "previous_baseline": previous_baseline,
        "accepted_baseline": accepted_baseline,
        "current_gate_unchanged": True,
        "read_back": read_project_gate(project_root),
        "delivery_route_sync": route_sync,
        "dry_run": args.dry_run,
    }
    if not synchronized:
        result["partial_commit"] = True
        result["error"] = (
            "Gate operation is incomplete. Inspect status and run operation-recover; do not repeat the Gate event."
        )
    return result


@transaction.guarded
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
        summary_seen = False
        for ref in runner_refs if isinstance(runner_refs, list) else []:
            try:
                path = evidence_path(project_root, str(ref))
                if path and is_evidence_summary_path(path):
                    summary_seen = True
                    runner_ok = runner_ok or validate_evidence_summary(project_root, path)["delivery_ready"]
                else:
                    runner = read_json(path) if path else {}
                    runner_ok = runner_ok or runner.get("status") in {"success", "warning"}
            except CollabError:
                continue
        if not summary_seen:
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


@transaction.guarded
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
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    print(json.dumps(data, ensure_ascii=False, indent=2))
