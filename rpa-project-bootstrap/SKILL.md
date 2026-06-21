---
name: rpa-project-bootstrap
description: Initialize a new RPA Python project from the remote rpa-dev-template on any machine. Use when the user says to create, initialize, clone, scaffold, reset, or prepare an RPA project with a project name and target directory. This skill clones the template, aligns project identity, generates sanitized project.json, validates handoff docs, initializes Git when requested, and stops before business logic.
---

# RPA Project Bootstrap

Use this skill to create a new project from the remote RPA Python template. This skill is intentionally portable: do not rely on local absolute paths such as `C:\Users\redballoon\...`.

## Primary Script

Use the bundled script by resolving it relative to this skill directory:

```powershell
python scripts/init_rpa_project.py --name "项目名" --target "C:\CodePJ\项目名"
```

Optional:

```powershell
python scripts/init_rpa_project.py --name "项目名" --target "D:\RPA\项目名" --template-url "https://github.com/redballoom/rpa-dev-template.git"
python scripts/init_rpa_project.py --name "项目名" --target "C:\tmp\项目名" --skip-git
python scripts/init_rpa_project.py --name "项目名" --target "C:\tmp\项目名" --force-overwrite
```

If the current agent cannot run relative paths from the skill directory, locate the current `SKILL.md` directory first and run:

```powershell
python "<skill_dir>\scripts\init_rpa_project.py" --name "项目名" --target "目标目录"
```

## Workflow

1. Resolve:
   - `project_name`
   - `target_dir`
   - `template_url`, default `https://github.com/redballoom/rpa-dev-template.git`
   - whether to initialize Git
2. Refuse to overwrite a non-empty target directory unless the user explicitly approves that exact path.
3. Run the initializer.
4. Read the final JSON result.
5. Report initialized path, missing handoff files, and commit hash.
6. Do not implement business logic during initialization.

## Handoff Expectations

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
- Initial commit hash, if Git was initialized.
- Whether `project.json` was generated and sanitized.
- Missing handoff files, if any.
- Test result, if run.
- Next prompt for business contract design.

Suggested next prompt:

```text
阅读 AGENTS.md、README.md、docs/OPERATION_GUIDE.md 和 docs/SHADOWBOT_INPUT_CONTRACT.md。根据我的业务目标先设计 input_{run_id}.json 的 tasks[].type 和 payload，不要先写 handler。等我确认契约后，再实现代码、示例和测试。
```

## Guardrails

- Do not keep the template `.git` history.
- Do not commit real secrets.
- Do not preserve runtime files such as root `input.json`, root `input_*.json`, `runner_*.json`, logs, crash snapshots, or data.
- Do not push to remote unless explicitly requested.
