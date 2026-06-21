# Bootstrap Checklist

Use this checklist after initializing a project.

## Identity

- Project name is non-empty.
- `project.template.json.project` matches the project name.
- `project.json.project` matches the project name when generated.
- `run.bat` project name matches the project name.

## Contract Files

- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `docs/RPA_PYTHON_BOUNDARY.md`
- `docs/ISSUE_FIX_WORKFLOW.md`
- `docs/examples/`
- `tests/`

The workflow skills live in the external skill repository, not inside every initialized project:

```text
https://github.com/redballoom/rpa-dev-template-skills
```

## Runtime Hygiene

- Root `input.json` is not tracked.
- Root `input_*.json` is ignored.
- `runner_*.json`, `logs/`, `crash_snapshots/`, and `data/` are ignored.
- `project.json` exists locally but secrets are blank.

## Next Step

Do not start implementation directly. First design:

- `input_{run_id}.json`
- `tasks[].type`
- `payload`
- output files
- status and exception semantics
