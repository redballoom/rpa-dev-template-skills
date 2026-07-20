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
5. Read `post_init_checks` from the script result:
   - `doctor`
6. If post-init checks were skipped or the template is older, report that clearly.
7. Report initialized path, missing template files, commit hash, and doctor result.
8. Do not implement business logic during initialization.

## Collaboration Bootstrap Handoff

This skill is the Project Bootstrap Core. It initializes a clean, runnable code project and stops there. Do not put Trellis task creation, Gate progress, Base sync, or workflow-Skill installation into `init_rpa_project.py`.

After the core initializer succeeds, recommend the collaboration bootstrap step when the user wants the project to enter the G0-G5 human/Agent workflow:

```powershell
trellis init `
  --registry gh:redballoom/rpa-trellis-spec-templates/marketplace `
  --template rpa-python-shadowbot `
  --codex

python <rpa-delivery-close-skill-dir>\scripts\rpa_collab.py `
  --project-root "<target_dir>" `
  bootstrap `
  --project-name "项目名" `
  --initial-gate G0 `
  --evidence "AGENTS.md" `
  --evidence "docs/OPERATION_GUIDE.md"
```

The collaboration bootstrap requires a full Trellis workspace by default, including `.trellis/spec`. It is responsible for creating or recognizing the Trellis delivery task, writing the initial G0/G1 local progress snapshot, and reading back `status` / `suggest`. If that step fails, report that the code project is still initialized and runnable, while collaboration tracking needs Trellis init, resume, or recovery.

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
先把项目接入本地协作进度（Trellis/Gate/status 回读），再根据业务目标设计 input_{run_id}.json 的 tasks[].type 和 payload，确认调用契约后再写 handler。
```

## Guardrails

- Do not keep the template `.git` history.
- Do not commit real secrets.
- Do not preserve runtime files such as root `input.json`, root `input_*.json`, `runner_*.json`, logs, crash snapshots, or data.
- Do not create Trellis Gate progress or Base records in the core initializer; hand off to the collaboration bootstrap layer.
- Do not push to remote unless explicitly requested.
