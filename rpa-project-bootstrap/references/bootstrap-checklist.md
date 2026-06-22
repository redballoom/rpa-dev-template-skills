# Bootstrap Checklist

Use this checklist after initializing a project.

## Identity

- Project name is non-empty.
- `project.template.json.project` matches the project name.
- `project.json.project` matches the project name when generated.
- `run.bat` project name matches the project name.
- If the user requested v2, a tag, or a non-main branch, initializer output records `template_ref`.

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

## Post-Init Checks

When the template supports them, initialization should run and report:

- `python tools/doctor.py`
- `python tools/handoff.py init --workspace initialized --project-path <target>`
- `python tools/handoff.py validate`

These results appear in the initializer JSON under `post_init_checks`. A skipped check means the template is older or the user passed `--skip-post-checks`; it should be reported, not hidden.

## Next Step

Do not start implementation directly. First design:

- `input_{run_id}.json`
- `tasks[].type`
- `payload`
- output files
- status and exception semantics
