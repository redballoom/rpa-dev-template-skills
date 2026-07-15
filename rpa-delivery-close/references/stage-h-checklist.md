# Stage H Final Calibration Checklist

Use this checklist before closing an RPA project or telling the user the delivery loop is complete. For an intermediate milestone, use only the sections that match the current event and do not require final archive evidence.

## 1. Requirement And Contract

- Business goal is recorded.
- ShadowBot responsibility is recorded.
- Python responsibility is recorded.
- `tasks[].type`, payload, output, status, exception semantics, and acceptance examples are known.
- The user explicitly confirmed the contract before implementation, or the final report clearly says this was a legacy or recovery project without prior contract confirmation.

## 2. Trellis Or Harness

When Trellis is present:

- The active task is identified.
- `prd.md` reflects the accepted scope.
- `design.md` is present when the project was complex enough to need design.
- `implement.md` or equivalent implementation plan reflects what was actually built.
- The task links to relevant commits, runner evidence, and acceptance conclusion.
- `task.json.meta.progress` reflects the current Gate, next action, owner, blocker, and evidence.
- Task-local `progress.md` contains the latest accepted or recovery checkpoint.
- The task is ready to complete or archive after user approval.

When Trellis is absent:

- Do not block delivery only because Trellis is absent.
- Use project docs, Git, runner evidence, and user acceptance as the record.
- State that the current Harness did not provide Trellis task evidence.

## 3. Git

- `git status` has no unexpected delivery changes.
- Runtime artifacts are not staged:
  - `runner_*.json`
  - `input*.json`
  - `logs/`
  - `crash_snapshots/`
  - `data/`
- There is a delivery-relevant commit or a clear pending commit plan.
- The final report includes the short hash and summary when committed.

## 4. Tests And Runner

- Relevant tests were run, or the report states why tests could not run.
- Accepted run has a `run_id`.
- `runner_{run_id}.json.status` is `success` or accepted `warning`.
- `pending_fix`, `fatal`, `failed`, and unresolved repeated `retryable_error` are not treated as delivered.
- Business output location and count or key sample are known when applicable.

## 5. ShadowBot And Business Acceptance

- ShadowBot-side call path is known:
  - generated input file
  - called `run.bat` or `runner.py`
  - read `runner_{run_id}.json`
- User checked the real business target or accepted output sample.
- External writes, deletes, or overwrites were explicitly authorized when involved.

## 6. Local Progress

- Local Trellis progress is sufficient to recover the project without chat or Base.
- The final checkpoint uses G5, `next_owner=none`, and names any remaining risk.
- Recovery entries are labeled as recovery rather than backdated as historical Gate events.

## 7. Optional Base Milestones

When a management Base is configured, prepare or sync only five high-value events. These events may be recorded as they happen; they do not need to wait until final project closure. Skip this section for a deliberately local-only project.

1. `PRD 待确认`
2. `允许开发`
3. `关键 Git 提交`
4. `联调结论/问题边界`
5. `业务验收结果`

Each event should have:

- linked project or project id
- event type
- short desensitized summary
- timestamp or date
- Trellis task id, when available
- commit hash, when relevant
- run_id, when relevant
- artifact references
- acceptance result
- idempotency key

## 8. Close Decision

Use one of three conclusions:

- `ready`: all required evidence is present; closure can proceed after any required user approval.
- `needs_user_review`: evidence exists, but the user must confirm business acceptance, write authorization, commit, archive, or Base update.
- `blocked`: required evidence is missing or failed; name the blocker and the smallest next action.
