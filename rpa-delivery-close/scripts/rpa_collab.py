#!/usr/bin/env python3
"""CLI for Hermes project Gates and Trellis engineering Task coordination."""

from __future__ import annotations

import argparse
from pathlib import Path

import hermes_controller as controller


def add_trellis_init_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--init-trellis", action="store_true")
    parser.add_argument("--trellis-cmd")
    parser.add_argument("--trellis-registry", default=controller.DEFAULT_TRELLIS_REGISTRY)
    parser.add_argument("--trellis-template", default=controller.DEFAULT_TRELLIS_TEMPLATE)
    parser.add_argument("--no-trellis-codex", dest="trellis_codex", action="store_false")
    parser.set_defaults(trellis_codex=True)


def add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--timestamp")
    parser.add_argument("--event-id")
    parser.add_argument("--reason", default="")
    parser.add_argument("--confirm-user-acceptance", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="RPA project root")
    parser.add_argument("--task", help="Task path or id")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Read Hermes, Trellis, Git, and runner facts")

    subparsers.add_parser("suggest", help="Recommend the next legal action")

    bootstrap = subparsers.add_parser("bootstrap", help="Initialize Hermes and attach one Trellis engineering Task")
    bootstrap.add_argument("--project-name", required=True)
    bootstrap.add_argument("--task-id")
    bootstrap.add_argument("--task-name")
    bootstrap.add_argument("--initial-gate", choices=("G0", "G1"), default="G0")
    bootstrap.add_argument("--allow-minimal", action="store_true")
    add_trellis_init_args(bootstrap)
    bootstrap.add_argument("--dry-run", action="store_true")

    close = subparsers.add_parser("gate-close", help="Close the current Hermes Gate after explicit user acceptance")
    close.add_argument("--accepted-gate", choices=controller.GATES, required=True)
    add_evidence_args(close)

    revalidate = subparsers.add_parser("gate-revalidate", help="Append a Gate revalidation without rewinding the project")
    revalidate.add_argument("--gate", choices=controller.GATES, required=True)
    add_evidence_args(revalidate)

    archive = subparsers.add_parser("archive-check", help="Check evidence before calling Trellis archive")
    archive.add_argument("--user-accepted", action="store_true")

    subparsers.add_parser("migration-preview", help="Read legacy Task-local Gate records without writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root)
    try:
        if args.command == "status":
            controller.print_json(controller.build_status(project_root, args.task))
        elif args.command == "suggest":
            status = controller.build_status(project_root, args.task)
            controller.print_json({"status": status, "suggestion": controller.suggest_action(status)})
        elif args.command == "bootstrap":
            controller.print_json(controller.bootstrap_collaboration(args))
        elif args.command == "gate-close":
            controller.print_json(controller.close_gate(args))
        elif args.command == "gate-revalidate":
            controller.print_json(controller.revalidate_gate(args))
        elif args.command == "archive-check":
            controller.print_json(controller.archive_check(args))
        elif args.command == "migration-preview":
            controller.print_json(controller.migration_preview(args))
        else:
            raise controller.CollabError(f"Unknown command: {args.command}")
    except controller.CollabError as exc:
        controller.print_json({"ok": False, "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
