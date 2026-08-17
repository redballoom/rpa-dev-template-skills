#!/usr/bin/env python3
"""Rejected legacy writer kept only to prevent accidental dual-writing."""

from __future__ import annotations

import json


class ProgressError(RuntimeError):
    pass


MESSAGE = (
    "Task-local Gate progress is retired. Use rpa_collab.py gate-close or "
    "gate-revalidate so project Gates are written only to .project-gates/."
)


def update_progress(_args: object) -> dict[str, object]:
    raise ProgressError(MESSAGE)


def main() -> int:
    print(json.dumps({"ok": False, "error": MESSAGE}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
