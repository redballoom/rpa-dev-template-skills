#!/usr/bin/env python3
"""Initialize an RPA Python project from the remote rpa-dev-template.

This script is portable. It does not depend on machine-specific paths.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE_URL = "https://github.com/redballoom/rpa-dev-template.git"

TEXT_SUFFIXES = {".bat", ".cmd", ".json", ".md", ".py", ".txt", ".ini", ".yaml", ".yml"}
IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", "logs", "crash_snapshots", "data"}
IGNORE_FILES = {".runner.lock", "input.json"}
IGNORE_PATTERNS = ["*.pyc", "runner_*.json", "input_*.json"]
SECRET_KEYS = {"api_key", "app_secret", "app_token", "feishu_webhook", "webhook", "token", "password", "secret"}


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError("command failed: %s\nstdout: %s\nstderr: %s" % (" ".join(cmd), proc.stdout, proc.stderr))
    return proc


def ensure_empty_or_missing(path: Path, force_overwrite: bool = False) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        raise RuntimeError("target exists and is not a directory: %s" % path)
    if force_overwrite:
        return
    visible = [item for item in path.iterdir() if item.name not in {".DS_Store", "Thumbs.db"}]
    if visible:
        raise RuntimeError("target directory is not empty: %s" % path)


def should_ignore(src: Path) -> bool:
    name = src.name
    if src.is_dir() and name in IGNORE_DIRS:
        return True
    if src.is_file() and name in IGNORE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in IGNORE_PATTERNS)


def copy_template(src_root: Path, dst_root: Path) -> None:
    dst_root.mkdir(parents=True, exist_ok=True)
    for src in src_root.iterdir():
        if should_ignore(src):
            continue
        dst = dst_root / src.name
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True,
                ignore=lambda directory, names: [n for n in names if should_ignore(Path(directory) / n)],
            )
        else:
            shutil.copy2(src, dst)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return None


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_project_name(root: Path, project_name: str) -> int:
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        text = read_text(path)
        if text is None:
            continue
        new_text = text.replace("开发模板", project_name).replace("rpa-dev-template", project_name)
        if new_text != text:
            write_text(path, new_text)
            changed += 1
    return changed


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lower = key.lower()
            if any(secret_key in lower for secret_key in SECRET_KEYS):
                cleaned[key] = ""
            else:
                cleaned[key] = scrub_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


def update_project_json(root: Path, project_name: str) -> None:
    project_json = root / "project.json"
    template_json = root / "project.template.json"
    if not project_json.exists():
        if not template_json.exists():
            raise RuntimeError("project.json and project.template.json are both missing")
        shutil.copy2(template_json, project_json)

    data = json.loads(project_json.read_text(encoding="utf-8-sig"))
    data = scrub_secrets(data)
    if isinstance(data, dict):
        data["project"] = project_name
        linear = data.get("linear")
        if isinstance(linear, dict):
            linear["project_name"] = project_name
    project_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_run_bat(root: Path, project_name: str) -> None:
    path = root / "run.bat"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    lines = []
    changed = False
    for line in text.splitlines():
        if line.strip().lower().startswith("set project="):
            lines.append("set PROJECT=%s" % project_name)
            changed = True
        else:
            lines.append(line)
    if changed:
        path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")


def validate_handoff_files(root: Path) -> list[str]:
    required = [
        "AGENTS.md",
        "README.md",
        "runner.py",
        "run.bat",
        "project.template.json",
        "docs/OPERATION_GUIDE.md",
        "docs/SHADOWBOT_INPUT_CONTRACT.md",
        "docs/RPA_PYTHON_BOUNDARY.md",
        "docs/examples",
        "tests",
    ]
    return [item for item in required if not (root / item).exists()]


def init_git(root: Path, project_name: str) -> str:
    run(["git", "init"], cwd=root)
    run(["git", "add", "-A"], cwd=root)
    commit = run(["git", "commit", "-m", "init: %s" % project_name], cwd=root, check=False)
    if commit.returncode != 0:
        raise RuntimeError("git commit failed:\n%s\n%s" % (commit.stdout.strip(), commit.stderr.strip()))
    rev = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    return rev.stdout.strip()


def run_optional_python_tool(root: Path, args: list[str]) -> dict[str, Any]:
    script = root / args[0]
    if not script.exists():
        return {
            "status": "skipped",
            "reason": "missing tool: %s" % args[0],
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }
    proc = run([sys.executable, *args], cwd=root, check=False)
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def run_post_init_checks(root: Path) -> dict[str, Any]:
    doctor = run_optional_python_tool(root, ["tools/doctor.py"])
    handoff_init = run_optional_python_tool(
        root,
        ["tools/handoff.py", "init", "--workspace", "initialized", "--project-path", str(root)],
    )
    handoff_validate = run_optional_python_tool(root, ["tools/handoff.py", "validate"])
    return {
        "doctor": doctor,
        "handoff_init": handoff_init,
        "handoff_validate": handoff_validate,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an RPA Python project from rpa-dev-template")
    parser.add_argument("--name", required=True, help="Project name, Chinese allowed")
    parser.add_argument("--target", default=os.getcwd(), help="Final target project directory")
    parser.add_argument("--template-url", default=DEFAULT_TEMPLATE_URL, help="Remote template Git URL")
    parser.add_argument("--skip-git", action="store_true", help="Do not initialize Git")
    parser.add_argument("--skip-post-checks", action="store_true", help="Do not run template doctor/handoff checks")
    parser.add_argument("--force-overwrite", action="store_true", help="Allow copying into a non-empty target directory")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary clone directory for debugging")
    args = parser.parse_args()

    project_name = args.name.strip()
    if not project_name:
        raise RuntimeError("--name cannot be empty")

    target = Path(args.target).expanduser().resolve()
    ensure_empty_or_missing(target, force_overwrite=args.force_overwrite)

    tmp_dir: Path | None = None
    result: dict[str, Any] = {
        "status": "error",
        "project_name": project_name,
        "target": str(target),
        "template_url": args.template_url,
        "missing_handoff_files": [],
        "git_commit": "",
        "post_init_checks": {},
    }

    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="rpa_template_"))
        clone_dir = tmp_dir / "template"
        run(["git", "clone", "--depth", "1", args.template_url, str(clone_dir)])
        copy_template(clone_dir, target)
        replace_project_name(target, project_name)
        update_project_json(target, project_name)
        update_run_bat(target, project_name)
        missing = validate_handoff_files(target)
        result["missing_handoff_files"] = missing
        if not args.skip_post_checks:
            result["post_init_checks"] = run_post_init_checks(target)
        if not args.skip_git:
            result["git_commit"] = init_git(target, project_name)
        result["status"] = "success"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        if tmp_dir and tmp_dir.exists() and not args.keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
