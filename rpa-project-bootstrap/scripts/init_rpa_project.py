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
IGNORE_FILES = {".runner.lock"}
IGNORE_PATTERNS = ["*.pyc"]
ROOT_RUNTIME_FILES = {"input.json"}
ROOT_RUNTIME_PATTERNS = ["runner_*.json", "input_*.json"]
SECRET_KEYS = {"api_key", "app_secret", "app_token", "feishu_webhook", "webhook", "token", "password", "secret"}


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            continue


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def print_json(data: dict[str, Any], stream: Any = None) -> None:
    target = stream if stream is not None else sys.stdout
    try:
        print(json.dumps(data, ensure_ascii=False, indent=2), file=target)
    except UnicodeEncodeError:
        print(json.dumps(data, ensure_ascii=True, indent=2), file=target)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError("command failed: %s\nstdout: %s\nstderr: %s" % (" ".join(cmd), proc.stdout, proc.stderr))
    return proc


def clone_template(template_url: str, clone_dir: Path, template_ref: str = "") -> None:
    cmd = ["git", "clone", "--depth", "1"]
    if template_ref:
        cmd.extend(["--branch", template_ref])
    cmd.extend([template_url, str(clone_dir)])
    run(cmd)


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


def should_ignore(src: Path, root: Path | None = None) -> bool:
    name = src.name
    if src.is_dir() and name in IGNORE_DIRS:
        return True
    if src.is_file() and name in IGNORE_FILES:
        return True
    if any(fnmatch.fnmatch(name, pat) for pat in IGNORE_PATTERNS):
        return True
    if root and src.is_file():
        try:
            rel = src.relative_to(root)
        except ValueError:
            rel = src
        if len(rel.parts) == 1:
            if name in ROOT_RUNTIME_FILES:
                return True
            return any(fnmatch.fnmatch(name, pat) for pat in ROOT_RUNTIME_PATTERNS)
    return False


def copy_template(src_root: Path, dst_root: Path) -> None:
    dst_root.mkdir(parents=True, exist_ok=True)
    for src in src_root.iterdir():
        if should_ignore(src, src_root):
            continue
        dst = dst_root / src.name
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True,
                ignore=lambda directory, names: [n for n in names if should_ignore(Path(directory) / n, src_root)],
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
        new_text = text.replace("开发模板", project_name)
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


def validate_template_files(root: Path) -> list[str]:
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
    directories = {"docs/examples", "tests"}
    return [item for item in required
            if not ((root / item).is_dir() if item in directories else (root / item).is_file())]


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
    if doctor["status"] == "ok":
        try:
            report = json.loads(doctor["stdout"])
            if not isinstance(report, dict) or report.get("status") != "ok":
                raise ValueError("doctor did not report status=ok")
        except (ValueError, TypeError) as exc:
            doctor["status"] = "failed"
            doctor["reason"] = str(exc)
    return {
        "doctor": doctor,
    }


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Initialize an RPA Python project from rpa-dev-template")
    parser.add_argument("--name", required=True, help="Project name, Chinese allowed")
    parser.add_argument("--target", default=os.getcwd(), help="Final target project directory")
    parser.add_argument("--template-url", default=DEFAULT_TEMPLATE_URL, help="Remote template Git URL")
    parser.add_argument("--template-ref", default="", help="Template branch or tag to clone, for example v2.0.0")
    parser.add_argument("--skip-git", action="store_true", help="Do not initialize Git")
    parser.add_argument("--skip-post-checks", action="store_true", help="Do not run the template doctor check")
    parser.add_argument("--force-overwrite", action="store_true", help="Allow copying into a non-empty target directory")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary clone directory for debugging")
    parser.add_argument("--verify-existing", action="store_true",
                        help="Recheck an existing directory without recopying, configuring or committing it")
    args = parser.parse_args()

    project_name = args.name.strip()
    target = Path(args.target).expanduser().resolve()

    tmp_dir: Path | None = None
    result: dict[str, Any] = {
        "status": "error",
        "project_name": project_name,
        "target": str(target),
        "template_url": args.template_url,
        "template_ref": args.template_ref,
        "missing_template_files": [],
        "git_commit": "",
        "post_init_checks": {},
        "stage": "preflight",
        "verification": "not_run",
        "verification_only": args.verify_existing,
        "target_modified": False,
        "template_commit": "",
        "recovery": {},
    }

    try:
        if not project_name:
            raise RuntimeError("--name cannot be empty")
        if args.verify_existing:
            if args.force_overwrite or args.skip_post_checks:
                raise RuntimeError("--verify-existing cannot be combined with --force-overwrite or --skip-post-checks")
            if not target.is_dir():
                raise RuntimeError("existing target directory is missing")
        else:
            ensure_empty_or_missing(target, force_overwrite=args.force_overwrite)
            result["stage"] = "clone"
            tmp_dir = Path(tempfile.mkdtemp(prefix="rpa_template_"))
            clone_dir = tmp_dir / "template"
            clone_template(args.template_url, clone_dir, args.template_ref.strip())
            result["template_commit"] = run(["git", "rev-parse", "HEAD"], cwd=clone_dir).stdout.strip()
            result["stage"] = "copy"
            # Copy/configuration can fail halfway; preserve the directory for inspection.
            result["target_modified"] = True
            copy_template(clone_dir, target)
            result["stage"] = "configure"
            replace_project_name(target, project_name)
            update_project_json(target, project_name)
            update_run_bat(target, project_name)
        result["stage"] = "required_files"
        missing = validate_template_files(target)
        result["missing_template_files"] = missing
        if missing:
            result["verification"] = "failed"
            raise RuntimeError("required template files or directories are missing or have the wrong type")
        result["stage"] = "doctor"
        if not args.skip_post_checks:
            result["post_init_checks"] = run_post_init_checks(target)
        else:
            result["post_init_checks"] = {"doctor": {"status": "skipped", "reason": "explicit --skip-post-checks", "returncode": None}}
        doctor = result["post_init_checks"].get("doctor", {})
        if doctor.get("status") == "failed" or doctor.get("returncode") not in (0, None):
            result["verification"] = "failed"
            raise RuntimeError("template doctor failed; no Git initialization or commit was attempted")
        if doctor.get("status") != "ok" or doctor.get("returncode") != 0:
            result["status"] = "incomplete"
            result["verification"] = "unverified"
            result["recovery"] = recovery_advice(target, project_name, "doctor")
            print_json(result)
            return 2
        result["verification"] = "passed"
        result["stage"] = "git"
        if not args.skip_git and not args.verify_existing:
            result["git_commit"] = init_git(target, project_name)
        result["status"] = "verified" if args.verify_existing else "success"
        result["stage"] = "complete"
        print_json(result)
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        result["recovery"] = recovery_advice(target, project_name, result["stage"])
        print_json(result, stream=sys.stderr)
        return 1
    finally:
        if tmp_dir and tmp_dir.exists() and not args.keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def recovery_advice(target: Path, project_name: str, stage: str) -> dict[str, Any]:
    return {
        "failed_stage": stage,
        "preserve_existing_files": True,
        "next_action": (
            "Fix the reported checks, then verify the existing directory. Verification does not finish a failed Git commit."
            if target.is_dir() else "Resolve the preflight/clone error and retry with an empty target."
        ),
        "verify_argv": [sys.executable, str(Path(__file__).resolve()), "--name", project_name,
                        "--target", str(target), "--verify-existing"] if target.is_dir() else [],
        "git_recovery": "Inspect Git status/index before explicitly committing; do not recopy the template to repair Git." if stage == "git" else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
