---
name: rpa-fix-loop
description: Diagnose and repair failed runs in projects created from rpa-dev-template. Use when runner_{run_id}.json has pending_fix, fatal, failed, repeated retryable_error, or when the user provides logs, crash_snapshots, Feishu notifications, Linear issues, or asks AI to fix a broken RPA/Python run. This skill reads fix_target when available, avoids changing Python for RPA/upstream issues by default, and verifies the smallest correct fix.
---

# RPA Failure Fix Loop

Use this skill after a run fails or repeatedly retries.

## Read First

Read available artifacts:

- `AGENTS.md`
- `docs/OPERATION_GUIDE.md`
- `docs/ISSUE_FIX_WORKFLOW.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `runner_{run_id}.json`
- `logs/run_{run_id}.log`
- `crash_snapshots/crash_{run_id}.json`

## Triage By Status

- `locked`: confirm ShadowBot retry behavior and concurrent execution. Do not patch code first.
- `retryable_error`: retry first unless repeated.
- `warning`: usually business/data issue. Fix code only if classification is wrong.
- `pending_fix`: inspect code, rule, environment, or dependency issue.
- `fatal`: inspect command args, missing files, malformed JSON, or config.

## Diagnose Boundary

Classify the issue:

- ShadowBot issue
- input contract issue
- Python business issue
- environment issue
- third-party issue

Prefer fixing Python only when the failure is reproducible from input files and project code.

When `runner_{run_id}.json.data.errors[].fix_target` exists, use it as the first routing signal:

- `python`: inspect and patch Python code, tests, or docs.
- `rpa`: explain the ShadowBot/input action needed; do not default to Python code changes.
- `upstream`: explain the external system, permission, network, or data-source issue; do not default to Python code changes.

If `fix_target` is missing, infer the boundary from evidence and say the confidence level.

## Repair Steps

1. Inspect runner output, logs, and snapshot.
2. Identify the smallest correct fix.
3. Add or update a test when practical.
4. Patch code or docs.
5. Run:

```powershell
python -m pytest tests/ -v
```

6. Clean runtime artifacts before final report.

## Final Report

Include:

- Failure status and likely root cause.
- Boundary: ShadowBot, input contract, Python, environment, or third party.
- Files changed.
- Tests run and result.
- Expected status after fix.
- Manual verification needed.
- Current verification status, residual risk, and suggested next action.

## Guardrails

- Do not parse Python traceback in ShadowBot.
- Do not mask `SystemException` as success.
- Do not change `runner.py` output protocol without explicit agreement.
- Do not push or merge without explicit user approval.

## Progress Handoff

When the diagnosis reaches a meaningful result, hand off to `rpa-delivery-close`:

- Record a `checkpoint` at the saved current Gate when a fix is implemented, verification is pending, the project is blocked, or the next owner changes.
- Include the runner status, failure boundary, test result, residual risk, and next owner as evidence or checkpoint context.
- Keep the Gate unchanged unless the user separately accepts that Gate; a successful repair is not automatic Gate acceptance.
- If local files and the saved progress disagree, use an explicit `recovery` entry rather than rewriting history.

Read back the Trellis snapshot before reporting the fix-loop handoff as recorded.
