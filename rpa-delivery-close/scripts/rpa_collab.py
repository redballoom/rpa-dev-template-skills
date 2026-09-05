#!/usr/bin/env python3
"""CLI for Project Gates and Trellis engineering Task coordination."""

from __future__ import annotations

import argparse
from pathlib import Path

import project_gate_controller as controller


def add_trellis_init_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--init-trellis", action="store_true")
    parser.add_argument("--trellis-cmd")
    parser.add_argument("--trellis-registry", default=controller.DEFAULT_TRELLIS_REGISTRY)
    parser.add_argument("--trellis-template", default=controller.DEFAULT_TRELLIS_TEMPLATE)
    parser.add_argument("--no-trellis-codex", dest="trellis_codex", action="store_false")
    parser.set_defaults(trellis_codex=True)


def add_evidence_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--baseline-commit", help="Exact Git commit accepted by the user; defaults to HEAD when available")
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

    subparsers.add_parser("status", help="Read Project Gate, Trellis, Git, and runner facts")

    subparsers.add_parser("suggest", help="Recommend the next legal action")

    evidence_check = subparsers.add_parser("evidence-check", help="Validate a portable sanitized run summary")
    evidence_check.add_argument("--summary", required=True, help="Path under evidence/runs ending in .summary.json")

    bootstrap = subparsers.add_parser("bootstrap", help="Initialize Project Gate tracking and attach one Trellis engineering Task")
    bootstrap.add_argument("--project-name", required=True)
    bootstrap.add_argument("--task-id")
    bootstrap.add_argument("--task-name")
    bootstrap.add_argument("--initial-gate", choices=("G0", "G1"), default="G0")
    bootstrap.add_argument("--allow-minimal", action="store_true")
    add_trellis_init_args(bootstrap)
    bootstrap.add_argument("--dry-run", action="store_true")

    close = subparsers.add_parser("gate-close", help="Close the current project Gate after explicit user acceptance")
    close.add_argument("--accepted-gate", choices=controller.GATES, required=True)
    add_evidence_args(close)

    revalidate = subparsers.add_parser("gate-revalidate", help="Append a Gate revalidation without rewinding the project")
    revalidate.add_argument("--gate", choices=controller.GATES, required=True)
    add_evidence_args(revalidate)

    amend = subparsers.add_parser("gate-amendment", help="Amend an accepted G0-G2 before the first G5 close without rewinding the project")
    amend.add_argument("--gate", choices=controller.AMENDABLE_GATES, required=True)
    add_evidence_args(amend)

    archive = subparsers.add_parser("archive-check", help="Check evidence before calling Trellis archive")
    archive.add_argument("--user-accepted", action="store_true")

    subparsers.add_parser("delivery-route-check", help="Validate the optional Issue-scoped Task delivery route")

    route = subparsers.add_parser("delivery-route-set", help="Write one confirmed Issue-scoped delivery route to a Trellis Task")
    route.add_argument("--change-class", required=True)
    route.add_argument("--entry", choices=controller.DELIVERY_REVIEWS, required=True)
    route.add_argument("--require-review", choices=controller.DELIVERY_REVIEWS, action="append", required=True)
    route.add_argument("--complete-review", choices=controller.DELIVERY_REVIEWS, action="append", default=[])
    route.add_argument("--project-revalidation", choices=controller.DELIVERY_REVIEWS, action="append", default=[])
    route.add_argument("--confirm-delivery-route", action="store_true")
    route.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("migration-preview", help="Read legacy Task-local and .hermes Gate records without writing")

    migrate = subparsers.add_parser(
        "migrate-project-gates",
        help="Move legacy .hermes Gate files to .project-gates without touching Hermes Agent plugins",
    )
    migrate.add_argument("--confirm-migration", action="store_true")
    migrate.add_argument("--timestamp")
    migrate.add_argument("--dry-run", action="store_true")
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
        elif args.command == "evidence-check":
            summary_path = controller.evidence_path(project_root, args.summary)
            if not summary_path or not controller.is_evidence_summary_path(summary_path):
                raise controller.CollabError("--summary must reference evidence/runs/*.summary.json")
            result = controller.validate_evidence_summary(project_root, summary_path)
            controller.print_json(result)
            if not result["valid"]:
                return 3
        elif args.command == "bootstrap":
            controller.print_json(controller.bootstrap_collaboration(args))
        elif args.command == "gate-close":
            result = controller.close_gate(args)
            controller.print_json(result)
            if not result.get("ok", True):
                return 3
        elif args.command == "gate-revalidate":
            result = controller.revalidate_gate(args)
            controller.print_json(result)
            if not result.get("ok", True):
                return 3
        elif args.command == "gate-amendment":
            result = controller.amend_gate(args)
            controller.print_json(result)
            if not result.get("ok", True):
                return 3
        elif args.command == "archive-check":
            controller.print_json(controller.archive_check(args))
        elif args.command == "delivery-route-check":
            controller.print_json(controller.check_delivery_route(project_root, args.task))
        elif args.command == "delivery-route-set":
            controller.print_json(controller.set_delivery_route(args))
        elif args.command == "migration-preview":
            controller.print_json(controller.migration_preview(args))
        elif args.command == "migrate-project-gates":
            controller.print_json(controller.migrate_project_gates(args))
        else:
            raise controller.CollabError(f"Unknown command: {args.command}")
    except controller.CollabError as exc:
        controller.print_json({"ok": False, "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
