#!/usr/bin/env python3
"""Update an RPA Trellis task progress snapshot and append a checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
NEXT_GATE = {"G0": "G1", "G1": "G2", "G2": "G3", "G3": "G4", "G4": "G5", "G5": "G5"}
OWNERS = ("agent", "user", "external", "none")
KINDS = ("checkpoint", "gate_close", "recovery")


class ProgressError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgressError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProgressError(f"Expected a JSON object in {path}")
    return data


def find_task(project_root: Path, task_input: str | None) -> tuple[Path, dict[str, Any]]:
    trellis_tasks = project_root / ".trellis" / "tasks"
    if not trellis_tasks.is_dir():
        raise ProgressError(f"Trellis tasks directory not found: {trellis_tasks}")

    task_files = sorted(trellis_tasks.rglob("task.json"))
    if task_input:
        direct = Path(task_input)
        direct_candidates = [direct] if direct.is_absolute() else [project_root / direct, trellis_tasks / direct]
        for candidate in direct_candidates:
            task_file = candidate if candidate.name == "task.json" else candidate / "task.json"
            if task_file.is_file():
                return task_file.parent, read_json(task_file)

        matches: list[tuple[Path, dict[str, Any]]] = []
        for task_file in task_files:
            data = read_json(task_file)
            if task_file.parent.name == task_input or data.get("id") == task_input or data.get("name") == task_input:
                matches.append((task_file.parent, data))
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ProgressError(f"Task not found by path, directory name, id, or name: {task_input}")
        raise ProgressError(f"Task identifier is ambiguous: {task_input}")

    active: list[tuple[Path, dict[str, Any]]] = []
    for task_file in task_files:
        if "archive" in task_file.relative_to(trellis_tasks).parts:
            continue
        active.append((task_file.parent, read_json(task_file)))
    if len(active) == 1:
        return active[0]
    if not active:
        raise ProgressError("No active Trellis task found; pass --task for an archived or explicit task")
    raise ProgressError("Multiple active Trellis tasks found; pass --task explicitly")


def one_line(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def make_checkpoint_id(payload: dict[str, Any], supplied: str | None) -> str:
    if supplied:
        return supplied
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "cp-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def validate_args(args: argparse.Namespace) -> None:
    if args.blocked and not one_line(args.block_reason or ""):
        raise ProgressError("--block-reason is required when --blocked is set")
    if args.kind == "gate_close" and not args.accepted_gate:
        raise ProgressError("--accepted-gate is required for kind=gate_close")
    if args.accepted_gate and args.kind != "recovery":
        expected = NEXT_GATE[args.accepted_gate]
        if args.gate != expected:
            raise ProgressError(
                f"Closing {args.accepted_gate} must leave current_gate at {expected}; got {args.gate}. "
                "Use kind=recovery for an explicit historical calibration."
            )


def build_snapshot(args: argparse.Namespace, timestamp: str, checkpoint_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "current_gate": args.gate,
        "current_work": one_line(args.current_work),
        "latest_checkpoint": one_line(args.latest_checkpoint),
        "next_action": one_line(args.next_action),
        "next_owner": args.next_owner,
        "blocked": bool(args.blocked),
        "block_reason": one_line(args.block_reason or "") if args.blocked else "",
        "updated_at": timestamp,
        "checkpoint_id": checkpoint_id,
        "evidence_refs": [one_line(item) for item in args.evidence if one_line(item)],
    }


def render_checkpoint(
    snapshot: dict[str, Any], kind: str, accepted_gate: str | None, checkpoint_id: str
) -> str:
    evidence = snapshot["evidence_refs"]
    lines = [
        "",
        f"<!-- checkpoint:{checkpoint_id} -->",
        f"## {snapshot['updated_at']} | {kind} | {snapshot['current_gate']}",
        "",
        f"- Checkpoint ID: `{checkpoint_id}`",
        f"- Current Gate: `{snapshot['current_gate']}`",
    ]
    if accepted_gate:
        lines.append(f"- Accepted Gate: `{accepted_gate}`")
    lines.extend(
        [
            f"- Current Work: {snapshot['current_work']}",
            f"- Latest Checkpoint: {snapshot['latest_checkpoint']}",
            f"- Next Action: {snapshot['next_action']}",
            f"- Next Owner: `{snapshot['next_owner']}`",
            f"- Blocked: `{'yes' if snapshot['blocked'] else 'no'}`",
        ]
    )
    if snapshot["block_reason"]:
        lines.append(f"- Block Reason: {snapshot['block_reason']}")
    lines.append("- Evidence:")
    lines.extend(f"  - `{item}`" for item in evidence) if evidence else lines.append("  - None recorded")
    lines.append("")
    return "\n".join(lines)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def update_progress(args: argparse.Namespace) -> dict[str, Any]:
    validate_args(args)
    project_root = Path(args.project_root).resolve()
    task_dir, task_data = find_task(project_root, args.task)
    task_file = task_dir / "task.json"
    timestamp = args.timestamp or datetime.now().astimezone().isoformat(timespec="seconds")

    identity_payload = {
        "task_id": task_data.get("id") or task_dir.name,
        "kind": args.kind,
        "gate": args.gate,
        "accepted_gate": args.accepted_gate,
        "current_work": one_line(args.current_work),
        "latest_checkpoint": one_line(args.latest_checkpoint),
        "next_action": one_line(args.next_action),
        "next_owner": args.next_owner,
        "blocked": bool(args.blocked),
        "block_reason": one_line(args.block_reason or ""),
        "evidence": [one_line(item) for item in args.evidence],
    }
    checkpoint_id = make_checkpoint_id(identity_payload, args.checkpoint_id)
    snapshot = build_snapshot(args, timestamp, checkpoint_id)

    meta = task_data.get("meta")
    if meta is None:
        meta = {}
        task_data["meta"] = meta
    if not isinstance(meta, dict):
        raise ProgressError(f"task.json meta must be an object: {task_file}")

    old_progress = meta.get("progress")
    if isinstance(old_progress, dict) and args.kind != "recovery":
        old_gate = old_progress.get("current_gate")
        if old_gate in GATES and args.kind == "checkpoint" and args.gate != old_gate:
            raise ProgressError(
                f"A checkpoint must keep current_gate at {old_gate}; got {args.gate}. "
                "Use gate_close after user acceptance or recovery for explicit calibration."
            )
        if old_gate in GATES and args.kind == "gate_close" and args.accepted_gate != old_gate:
            raise ProgressError(
                f"The saved current_gate is {old_gate}, so gate_close must accept {old_gate}; "
                f"got {args.accepted_gate}."
            )
    no_change = False
    if isinstance(old_progress, dict) and old_progress.get("checkpoint_id") == checkpoint_id:
        compare_keys = set(snapshot) - {"updated_at"}
        old_comparable = {key: old_progress.get(key) for key in compare_keys}
        new_comparable = {key: snapshot.get(key) for key in compare_keys}
        if old_comparable != new_comparable:
            raise ProgressError(
                f"Checkpoint id {checkpoint_id} already exists with different content; "
                "use a new checkpoint id for a corrective recovery entry."
            )
        snapshot["updated_at"] = old_progress.get("updated_at", snapshot["updated_at"])
        no_change = True
    meta["progress"] = {**(old_progress if isinstance(old_progress, dict) else {}), **snapshot}

    progress_file = task_dir / "progress.md"
    marker = f"<!-- checkpoint:{checkpoint_id} -->"
    existing_history = progress_file.read_text(encoding="utf-8") if progress_file.exists() else ""
    history_has_checkpoint = marker in existing_history

    if not args.dry_run:
        atomic_write_json(task_file, task_data)
        if not history_has_checkpoint:
            if not progress_file.exists():
                progress_file.write_text(
                    "# RPA Progress Checkpoints\n\n"
                    "> Current state lives in `task.json.meta.progress`; this file is append-only history.\n",
                    encoding="utf-8",
                )
            with progress_file.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(render_checkpoint(snapshot, args.kind, args.accepted_gate, checkpoint_id))

    return {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "task_file": str(task_file),
        "progress_file": str(progress_file),
        "checkpoint_id": checkpoint_id,
        "snapshot_changed": not no_change,
        "history_appended": not history_has_checkpoint,
        "progress": snapshot,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="RPA project root; defaults to current directory")
    parser.add_argument("--task", help="Task path, directory name, task id, or task name")
    parser.add_argument("--kind", choices=KINDS, default="checkpoint")
    parser.add_argument("--gate", choices=GATES, required=True, help="Gate currently waiting to close after this update")
    parser.add_argument("--accepted-gate", choices=GATES, help="Gate accepted by the user in this checkpoint")
    parser.add_argument("--current-work", required=True)
    parser.add_argument("--latest-checkpoint", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--next-owner", choices=OWNERS, required=True)
    parser.add_argument("--blocked", action="store_true")
    parser.add_argument("--block-reason", default="")
    parser.add_argument("--evidence", action="append", default=[], help="Repeat for multiple evidence references")
    parser.add_argument("--checkpoint-id", help="Stable idempotency key; generated from content when omitted")
    parser.add_argument("--timestamp", help="ISO-8601 timestamp override for recovery or tests")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = update_progress(args)
    except ProgressError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
