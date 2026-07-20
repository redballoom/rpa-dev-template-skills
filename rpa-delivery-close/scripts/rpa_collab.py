#!/usr/bin/env python3
"""Inspect and guard RPA collaboration progress stored in Trellis tasks."""

from __future__ import annotations

import argparse
import os
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import update_trellis_progress as progress_writer


GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
NEXT_GATE = {"G0": "G1", "G1": "G2", "G2": "G3", "G3": "G4", "G4": "G5", "G5": "G5"}
DEFAULT_TRELLIS_REGISTRY = "gh:redballoom/rpa-trellis-spec-templates/marketplace"
DEFAULT_TRELLIS_TEMPLATE = "rpa-python-shadowbot"


class CollabError(RuntimeError):
    pass


def slugify_task_id(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9._\-\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-._")
    if not text:
        raise CollabError("Task id cannot be empty")
    return text


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollabError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CollabError(f"Expected JSON object in {path}")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
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
        raise CollabError(
            "Cannot find Trellis CLI. Pass --trellis-cmd, set RPA_TRELLIS_CMD, or install trellis in PATH."
        )

    command = [
        cmd,
        "init",
        "--registry",
        args.trellis_registry,
        "--template",
        args.trellis_template,
    ]
    if args.trellis_codex:
        command.append("--codex")

    if args.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "command": command,
            "cwd": str(project_root),
        }

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
        raise CollabError("Trellis init completed but .trellis/spec was not found; workspace is incomplete.")
    return result


def create_minimal_task(project_root: Path, task_id: str, task_name: str, dry_run: bool = False) -> tuple[Path, dict[str, Any]]:
    task_slug = slugify_task_id(task_id)
    task_dir = project_root / ".trellis" / "tasks" / task_slug
    task_file = task_dir / "task.json"
    if task_file.exists():
        return task_file, read_json(task_file)

    task_data = {
        "id": task_slug,
        "name": task_name,
        "status": "in_progress",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "meta": {},
    }
    if not dry_run:
        task_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(task_file, task_data)
        progress_file = task_dir / "progress.md"
        if not progress_file.exists():
            progress_file.write_text(
                "# RPA Progress Checkpoints\n\n"
                "> Current state lives in `task.json.meta.progress`; this file is append-only history.\n",
                encoding="utf-8",
            )
    return task_file, task_data


def is_archive_path(task_file: Path, tasks_root: Path) -> bool:
    try:
        return "archive" in task_file.relative_to(tasks_root).parts
    except ValueError:
        return False


def find_task_files(project_root: Path) -> list[Path]:
    tasks_root = project_root / ".trellis" / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(tasks_root.rglob("task.json"))


def has_progress_gate(task_data: dict[str, Any]) -> bool:
    meta = task_data.get("meta")
    if not isinstance(meta, dict):
        return False
    progress = meta.get("progress")
    if not isinstance(progress, dict):
        return False
    return progress.get("current_gate") in GATES


def match_task(project_root: Path, task_input: str | None) -> tuple[Path, dict[str, Any]]:
    task_files = find_task_files(project_root)
    if not task_files:
        raise CollabError(f"No Trellis task.json files found under {project_root / '.trellis' / 'tasks'}")

    tasks_root = project_root / ".trellis" / "tasks"
    if task_input:
        direct = Path(task_input)
        candidates = [direct] if direct.is_absolute() else [project_root / direct, tasks_root / direct]
        for candidate in candidates:
            task_file = candidate if candidate.name == "task.json" else candidate / "task.json"
            if task_file.is_file():
                return task_file, read_json(task_file)

        matches: list[tuple[Path, dict[str, Any]]] = []
        for task_file in task_files:
            task_data = read_json(task_file)
            if task_file.parent.name == task_input or task_data.get("id") == task_input or task_data.get("name") == task_input:
                matches.append((task_file, task_data))
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise CollabError(f"Task not found: {task_input}")
        raise CollabError(f"Task identifier is ambiguous: {task_input}")

    active: list[tuple[Path, dict[str, Any]]] = []
    for task_file in task_files:
        if is_archive_path(task_file, tasks_root):
            continue
        task_data = read_json(task_file)
        if task_data.get("status") != "completed":
            active.append((task_file, task_data))

    active_progress = [(path, data) for path, data in active if has_progress_gate(data)]
    if len(active_progress) == 1:
        return active_progress[0]
    if len(active_progress) > 1:
        raise CollabError("Multiple active Trellis tasks have local progress; pass --task explicitly")

    progress_tasks: list[tuple[Path, dict[str, Any]]] = []
    for task_file in task_files:
        task_data = read_json(task_file)
        if has_progress_gate(task_data):
            progress_tasks.append((task_file, task_data))
    if len(progress_tasks) == 1:
        return progress_tasks[0]
    if len(progress_tasks) > 1:
        raise CollabError("Multiple Trellis tasks have local progress; pass --task explicitly")

    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        raise CollabError("Multiple active Trellis tasks found and none has local progress; pass --task explicitly")

    non_archived = [(path, read_json(path)) for path in task_files if not is_archive_path(path, tasks_root)]
    if len(non_archived) == 1:
        return non_archived[0]
    raise CollabError("No active Trellis task found; pass --task for archived or completed tasks")


def latest_runner(project_root: Path) -> dict[str, Any] | None:
    candidates = sorted(project_root.glob("runner_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            data = read_json(candidate)
        except CollabError:
            continue
        return {
            "path": str(candidate),
            "status": data.get("status"),
            "run_id": data.get("run_id") or candidate.stem.removeprefix("runner_"),
        }
    return None


def git_info(project_root: Path) -> dict[str, Any]:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return {"available": False}

    def run_git(args: list[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""

    return {
        "available": True,
        "head": run_git(["log", "-1", "--oneline"]),
        "dirty": bool(run_git(["status", "--short"])),
    }


def build_status(project_root: Path, task_input: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    task_file, task_data = match_task(project_root, task_input)
    tasks_root = project_root / ".trellis" / "tasks"
    progress = task_data.get("meta", {}).get("progress") if isinstance(task_data.get("meta"), dict) else None
    progress = progress if isinstance(progress, dict) else None

    current_gate = progress.get("current_gate") if progress else None
    task_status = task_data.get("status")
    archived = is_archive_path(task_file, tasks_root)
    warnings: list[dict[str, str]] = []

    if not progress:
        warnings.append({"code": "missing_progress", "message": "Task has no task.json.meta.progress snapshot"})
    if progress and current_gate not in GATES:
        warnings.append({"code": "invalid_gate", "message": f"Unknown current_gate: {current_gate}"})
    if progress and task_status == "completed" and progress.get("next_owner") != "none":
        warnings.append(
            {
                "code": "lifecycle_drift",
                "message": "Task is completed but progress still has an active next_owner",
            }
        )
    if progress and archived and progress.get("next_owner") != "none":
        warnings.append(
            {
                "code": "archive_drift",
                "message": "Task is archived but progress still expects follow-up work",
            }
        )
    if progress and task_status == "completed" and current_gate != "G5":
        warnings.append(
            {
                "code": "completed_before_g5",
                "message": "Task is completed while current_gate is not G5",
            }
        )

    return {
        "ok": True,
        "project_root": str(project_root),
        "task_file": str(task_file),
        "task_id": task_data.get("id") or task_file.parent.name,
        "task_status": task_status,
        "archived": archived,
        "progress": progress,
        "warnings": warnings,
        "runner": latest_runner(project_root),
        "git": git_info(project_root),
    }


def bootstrap_collaboration(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    trellis_init_result: dict[str, Any] | None = None
    full_workspace = has_full_trellis_workspace(project_root)
    if not full_workspace:
        if args.init_trellis:
            trellis_init_result = run_trellis_init(project_root, args)
            full_workspace = True if args.dry_run else has_full_trellis_workspace(project_root)
        elif not args.allow_minimal:
            raise CollabError(
                "Full Trellis workspace is missing: expected .trellis/spec. "
                "Run trellis init first or pass --init-trellis. "
                "--allow-minimal is only for explicit degraded local fallback."
            )

    task_identifier = args.task or args.task_id or slugify_task_id(args.project_name)
    task_name = args.task_name or args.project_name
    created_task = False
    initialized_progress = False

    try:
        task_file, task_data = match_task(project_root, task_identifier)
    except CollabError:
        task_file, task_data = create_minimal_task(project_root, task_identifier, task_name, dry_run=args.dry_run)
        created_task = True

    progress = task_data.get("meta", {}).get("progress") if isinstance(task_data.get("meta"), dict) else None
    if isinstance(progress, dict):
        status = build_status(project_root, str(task_file.parent))
        return {
            "ok": True,
            "created_task": created_task,
            "initialized_progress": False,
            "trellis_workspace": "full" if full_workspace else "minimal",
            "trellis_init": trellis_init_result,
            "reason": "Existing local progress snapshot preserved",
            "status": status,
            "suggestion": suggest_action(status),
        }

    if args.dry_run and created_task:
        return {
            "ok": True,
            "dry_run": True,
            "created_task": True,
            "initialized_progress": True,
            "trellis_workspace": "full" if full_workspace else "minimal",
            "trellis_init": trellis_init_result,
            "task_file": str(task_file),
            "planned_progress": {
                "current_gate": args.initial_gate,
                "current_work": args.current_work,
                "latest_checkpoint": args.latest_checkpoint,
                "next_action": args.next_action,
                "next_owner": args.next_owner,
                "evidence_refs": args.evidence or [],
            },
        }

    writer_args = argparse.Namespace(
        project_root=str(project_root),
        task=str(task_file.parent),
        kind="checkpoint",
        gate=args.initial_gate,
        accepted_gate=None,
        current_work=args.current_work,
        latest_checkpoint=args.latest_checkpoint,
        next_action=args.next_action,
        next_owner=args.next_owner,
        blocked=False,
        block_reason="",
        evidence=args.evidence or [],
        checkpoint_id=args.checkpoint_id,
        timestamp=args.timestamp,
        dry_run=args.dry_run,
    )
    progress_result = progress_writer.update_progress(writer_args)
    initialized_progress = True
    status = build_status(project_root, str(task_file.parent))
    return {
        "ok": True,
        "created_task": created_task,
        "initialized_progress": initialized_progress,
        "trellis_workspace": "full" if full_workspace else "minimal",
        "trellis_init": trellis_init_result,
        "progress_result": progress_result,
        "status": status,
        "suggestion": suggest_action(status),
    }


def suggest_action(status: dict[str, Any]) -> dict[str, Any]:
    warnings = {warning["code"] for warning in status.get("warnings", [])}
    progress = status.get("progress") or {}
    gate = progress.get("current_gate")

    if "missing_progress" in warnings:
        action = "recovery"
        reason = "No local progress snapshot exists; inspect project evidence before initializing progress."
    elif "lifecycle_drift" in warnings or "archive_drift" in warnings or "completed_before_g5" in warnings:
        action = "recovery"
        reason = "Task lifecycle and progress snapshot disagree; write an explicit calibration entry."
    elif progress.get("blocked"):
        action = "checkpoint"
        reason = "Project is blocked; keep the current Gate and update owner or unblock evidence."
    elif gate == "G5" and status.get("task_status") != "completed":
        action = "finish"
        reason = "Current Gate is G5; run final evidence calibration before marking completed."
    elif gate in GATES:
        action = "continue_current_gate"
        reason = "Continue gathering evidence for the current Gate; close it only after user acceptance."
    else:
        action = "inspect"
        reason = "Gate is unclear; inspect task files and evidence before writing progress."

    return {
        "ok": True,
        "recommended_action": action,
        "reason": reason,
        "current_gate": gate,
        "next_gate_if_accepted": NEXT_GATE.get(gate),
    }


def update_with_writer(args: argparse.Namespace, kind: str, gate: str, accepted_gate: str | None = None) -> dict[str, Any]:
    writer_args = argparse.Namespace(
        project_root=str(Path(args.project_root).resolve()),
        task=args.task,
        kind=kind,
        gate=gate,
        accepted_gate=accepted_gate,
        current_work=args.current_work,
        latest_checkpoint=args.latest_checkpoint,
        next_action=args.next_action,
        next_owner=args.next_owner,
        blocked=bool(getattr(args, "blocked", False)),
        block_reason=getattr(args, "block_reason", ""),
        evidence=args.evidence or [],
        checkpoint_id=args.checkpoint_id,
        timestamp=args.timestamp,
        dry_run=args.dry_run,
    )
    return progress_writer.update_progress(writer_args)


def close_gate(args: argparse.Namespace) -> dict[str, Any]:
    status = build_status(Path(args.project_root), args.task)
    progress = status.get("progress") or {}
    current_gate = progress.get("current_gate")
    if current_gate != args.accepted_gate:
        raise CollabError(f"Saved current_gate is {current_gate}; cannot accept {args.accepted_gate}")
    next_gate = args.gate or NEXT_GATE[args.accepted_gate]
    result = update_with_writer(args, "gate_close", next_gate, args.accepted_gate)
    result["read_back"] = build_status(Path(args.project_root), args.task)
    return result


def finish(args: argparse.Namespace) -> dict[str, Any]:
    status = build_status(Path(args.project_root), args.task)
    progress = status.get("progress") or {}
    if progress.get("current_gate") != "G5":
        raise CollabError(f"finish requires current_gate G5; got {progress.get('current_gate')}")
    if progress.get("blocked"):
        raise CollabError("finish cannot run while progress is blocked")

    args.gate = "G5"
    args.next_owner = "none"
    result = update_with_writer(args, "checkpoint", "G5")

    if not args.dry_run:
        task_file = Path(result["task_file"])
        task_data = read_json(task_file)
        task_data["status"] = "completed"
        task_data.setdefault("completedAt", date.today().isoformat())
        write_json_atomic(task_file, task_data)

    read_back = build_status(Path(args.project_root), args.task)
    drift_codes = {warning["code"] for warning in read_back.get("warnings", [])}
    if drift_codes.intersection({"lifecycle_drift", "completed_before_g5"}):
        raise CollabError(f"finish read-back still has lifecycle drift: {sorted(drift_codes)}")
    result["read_back"] = read_back
    return result


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="RPA project root")
    parser.add_argument("--task", help="Task path, directory name, task id, or task name")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Read current Trellis/Git/runner status without writing")
    subparsers.add_parser("suggest", help="Read status and recommend the next legal workflow action")

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Attach an initialized project to local Trellis/Gate progress and read it back",
    )
    bootstrap_parser.add_argument("--project-name", required=True)
    bootstrap_parser.add_argument("--task-id", help="Main delivery task id; defaults to project-name slug")
    bootstrap_parser.add_argument("--task-name", help="Human-readable task name; defaults to project-name")
    bootstrap_parser.add_argument("--initial-gate", choices=("G0", "G1"), default="G0")
    bootstrap_parser.add_argument("--init-trellis", action="store_true", help="Run trellis init when .trellis/spec is missing")
    bootstrap_parser.add_argument("--trellis-cmd", help="Path to trellis or trellis.cmd")
    bootstrap_parser.add_argument("--trellis-registry", default=DEFAULT_TRELLIS_REGISTRY)
    bootstrap_parser.add_argument("--trellis-template", default=DEFAULT_TRELLIS_TEMPLATE)
    bootstrap_parser.add_argument("--no-trellis-codex", dest="trellis_codex", action="store_false")
    bootstrap_parser.set_defaults(trellis_codex=True)
    bootstrap_parser.add_argument(
        "--allow-minimal",
        action="store_true",
        help="Allow degraded task-only .trellis fallback when full Trellis workspace is absent",
    )
    bootstrap_parser.add_argument("--current-work", default="Collaboration bootstrap initialized")
    bootstrap_parser.add_argument("--latest-checkpoint", default="Project is ready for requirement alignment")
    bootstrap_parser.add_argument("--next-action", default="Align G0 requirement scope with the user")
    bootstrap_parser.add_argument("--next-owner", choices=("agent", "user", "external", "none"), default="agent")
    bootstrap_parser.add_argument("--evidence", action="append", default=[])
    bootstrap_parser.add_argument("--checkpoint-id")
    bootstrap_parser.add_argument("--timestamp")
    bootstrap_parser.add_argument("--dry-run", action="store_true")

    gate_close = subparsers.add_parser("gate-close", help="Close the saved current Gate after user acceptance")
    gate_close.add_argument("--accepted-gate", choices=GATES, required=True)
    gate_close.add_argument("--gate", choices=GATES, help="Resulting current Gate; defaults to the next Gate")
    add_progress_args(gate_close)

    finish_parser = subparsers.add_parser("finish", help="Finalize G5 progress and mark the Trellis task completed")
    add_progress_args(finish_parser)
    return parser


def add_progress_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--current-work", required=True)
    parser.add_argument("--latest-checkpoint", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--next-owner", choices=("agent", "user", "external", "none"), default="agent")
    parser.add_argument("--blocked", action="store_true")
    parser.add_argument("--block-reason", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--checkpoint-id")
    parser.add_argument("--timestamp")
    parser.add_argument("--dry-run", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            print_json(build_status(Path(args.project_root), args.task))
        elif args.command == "suggest":
            status = build_status(Path(args.project_root), args.task)
            print_json({"status": status, "suggestion": suggest_action(status)})
        elif args.command == "bootstrap":
            print_json(bootstrap_collaboration(args))
        elif args.command == "gate-close":
            print_json(close_gate(args))
        elif args.command == "finish":
            print_json(finish(args))
        else:
            raise CollabError(f"Unknown command: {args.command}")
    except (CollabError, progress_writer.ProgressError) as exc:
        print_json({"ok": False, "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
