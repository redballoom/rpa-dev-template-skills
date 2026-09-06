---
name: rpa-project-bootstrap
description: Initialize a new RPA Python project from the remote rpa-dev-template on any machine. Use when the user says to create, initialize, clone, scaffold, reset, or prepare an RPA project with a project name and target directory. This skill clones the template, aligns project identity, generates sanitized project.json, validates core template files, initializes Git when requested, runs the template doctor when available, and stops before business logic.
---

# RPA Project Bootstrap

Use this skill to create a new project from the remote RPA Python template. This skill is intentionally portable: do not rely on developer-specific absolute paths such as `C:\Users\someone\...`.

## Primary Script

Use the bundled script by resolving it relative to this skill directory:

```powershell
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名"
```

Optional:

```powershell
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名" --template-url "https://github.com/redballoom/rpa-dev-template.git"
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名" --template-ref "codex/workflow-productization"
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名" --skip-git
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名" --skip-post-checks
python scripts/init_rpa_project.py --name "项目名" --target ".\项目名" --force-overwrite
```

These are examples only. Always prefer the target directory explicitly provided by the user.

If the current agent cannot run relative paths from the skill directory, locate the current `SKILL.md` directory first and run:

```powershell
python "<skill_dir>\scripts\init_rpa_project.py" --name "项目名" --target "目标目录"
```

## Workflow

1. Resolve:
   - `project_name`
   - `target_dir`
   - `template_url`, default `https://github.com/redballoom/rpa-dev-template.git`
   - `template_ref` if the user asks for a branch, tag, v2, workflow-enhanced template, or experimental template
   - whether to initialize Git
2. Refuse to overwrite a non-empty target directory unless the user explicitly approves that exact path.
3. Run the initializer.
4. Read the final JSON result.
   `status=success` requires completed core checks. `status=verified` is a recheck only, not a new initialization or a repaired Git commit. Treat `incomplete` (exit 2) as unverified and `error` (exit 1) as failure; neither authorizes the collaboration handoff. Read `stage`, `verification`, `target_modified`, and `recovery` before retrying.
5. Read `post_init_checks` from the script result:
   - `doctor`
6. If post-init checks were skipped or the template is older, report that clearly.
7. Report initialized path, missing template files, commit hash, and doctor result.
8. Do not implement business logic during initialization.

## Failure and recheck

Missing/wrong-type required files, failed doctor, malformed doctor output, or doctor reporting failure even with exit code 0 stop before Git initialization. Explicit `--skip-post-checks` and old templates without doctor return `incomplete`, not success. The clone's exact `template_commit` is reported when available.

Preserve a partially initialized directory. After the reported problem is repaired, recheck it without recopying, scrubbing local configuration or committing:

```powershell
python "<skill_dir>\scripts\init_rpa_project.py" --name "项目名" --target "目标目录" --verify-existing
```

This executes the target's doctor and required-file checks; it does not modify project identity or finish a failed Git operation. For Git failure, inspect the preserved index/status and explicitly finish the intended commit after resolving identity or repository problems. For clone failure, retry against an empty target after resolving the source problem. Ordinary retry refuses a non-empty target; do not use `--force-overwrite` as automatic recovery. Read `recovery.verify_argv` as an argument array, not a shell command string.

Core verification does not install Trellis, create a Task/Gate, or prove that remote deployment is reproducible. Perform the collaboration handoff only when a real workflow or explicitly scoped integration test requires it.

## Collaboration Bootstrap Handoff

This skill is the Project Bootstrap Core. It initializes a clean, runnable code project and stops there. Do not put Trellis task creation, Gate progress, Base sync, or workflow-Skill installation into `init_rpa_project.py`.

After the core initializer succeeds, run the collaboration bootstrap when the project enters the G0-G5 human/Agent workflow:

```powershell
npx --yes @mindfoldhq/trellis@0.6.14 init `
  --registry gh:redballoom/rpa-trellis-spec-templates `
  --template rpa-python-shadowbot `
  --codex

python <rpa-delivery-close-skill-dir>\scripts\rpa_collab.py `
  --project-root "<target_dir>" `
  bootstrap `
  --project-name "项目名" `
  --initial-gate G0
```

The collaboration bootstrap requires a full Trellis workspace by default, including `.trellis/spec`. It creates or recognizes one Trellis engineering Task, creates `.project-gates/project.json` and `.project-gates/gate-history.md`, writes `session_auto_commit: false` to `.trellis/config.yaml`, and reads the result back. It must not add `current_gate` or Gate history to Trellis Task metadata. If this step fails, report that the code project is still initialized and runnable while collaboration governance needs initialization or recovery.

If an existing project contains legacy `.hermes/project.json`, do not bootstrap a second Gate state. Hand off to `rpa-delivery-close` for `migration-preview` and the explicitly confirmed `migrate-project-gates` operation. Never move or delete `.hermes/plugins/` or other Hermes Agent files.

## Template Expectations

The initialized project should include:

- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `docs/RPA_PYTHON_BOUNDARY.md`
- `docs/examples/`
- `tests/`

The reusable workflow skills are installed from this external repository, not copied into every initialized project.

## Validation

If dependencies are available:

```powershell
python -m pytest tests/ -v
```

If tests cannot run, report why and give the exact command for later.

## Final Report

Include:

- Project path.
- Template URL and template ref, if one was used.
- Initial commit hash, if Git was initialized.
- Whether `project.json` was generated and sanitized.
- Missing template files, if any.
- Test result, if run.
- Doctor result, if supported by the template.

Suggested next action for the user:

```text
先用 Trellis 建立工程 Task、用 Project Gate Controller 建立项目 Gate 并回读状态，再根据业务目标设计 input_{run_id}.json 的 tasks[].type 和 payload，确认调用契约后再写 handler。
```

## Guardrails

- Do not keep the template `.git` history.
- Do not commit real secrets.
- Do not preserve runtime files such as root `input.json`, root `input_*.json`, `runner_*.json`, logs, crash snapshots, or data.
- Do not create Gate progress in Trellis or Base records in the core initializer; hand off to the Project Gate Controller collaboration bootstrap layer.
- Do not create project Gate files under `.hermes/`; use `.project-gates/` so the project remains compatible with Hermes Agent and other harnesses.
- Do not push to remote unless explicitly requested.
