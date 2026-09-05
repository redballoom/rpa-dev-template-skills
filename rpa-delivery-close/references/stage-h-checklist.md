# Stage H Final Calibration Checklist

Use this checklist before closing an RPA project or telling the user the delivery loop is complete. For an intermediate milestone, use only the sections that match the current event and do not require final archive evidence.

## 1. Requirement And Contract

- Business goal is recorded.
- ShadowBot responsibility is recorded.
- Python responsibility is recorded.
- `tasks[].type`, payload, output, status, exception semantics, and acceptance examples are known.
- The user explicitly confirmed the contract before implementation, or the final report clearly says this was a legacy or recovery project without prior contract confirmation.

## 2. Project Gate Controller And Trellis

Project Gate Controller:

- `.project-gates/project.json` contains the only project `current_gate`.
- `.project-gates/gate-history.md` contains the accepted Gate close or revalidation event when applicable.
- `accepted_baseline.commit` identifies the last Git version accepted by the user.
- `status.delivery_baseline` does not report `unaccepted_delivery_drift`, `history_diverged`, or a missing accepted commit.
- Legacy `.hermes/project.json` and `.hermes/gate-history.md` are absent; `.hermes/plugins/` may remain for Hermes Agent.
- The Gate event references evidence rather than copying its content.
- G5 maintenance keeps `current_gate=G5`; major changes append revalidation events.
- G0-G2 corrections before the first G5 append `gate-amendment` events without rewriting the original close.

Trellis:

- The active task is identified.
- `prd.md` reflects the accepted scope.
- `design.md` is present when the project was complex enough to need design.
- `implement.md` or equivalent implementation plan reflects what was actually built.
- The task links to relevant commits, runner evidence, and acceptance conclusion.
- When available, the task links to `evidence/runs/{run_id}.summary.json`; the Controller reports it as valid and `delivery_ready`.
- The Task does not contain `meta.progress.current_gate` or Task-local Gate history.
- `meta.delivery_state` contains only Task-owned delivery state.
- `meta.delivery_requirements` explicitly records boolean `require_pr`,
  `require_runner`, and `require_user_acceptance`; no requirement is inferred from
  a missing field.
- `archive-check` returns `ready=true` before Trellis archive.

When Trellis is absent:

- Do not claim a formal Task archive.
- Use Project Gate Controller, project docs, Git, runner evidence, and user acceptance to report what is known.
- State that the project did not provide Trellis Task evidence.

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
- Portable evidence summary is integrity-valid, has `working_tree_clean=true`, matches current `HEAD`, and records `run.bat`; otherwise it is not delivery evidence.
- `pending_fix`, `fatal`, `failed`, and unresolved repeated `retryable_error` are not treated as delivered.
- Business output location and count or key sample are known when applicable.

## 5. ShadowBot And Business Acceptance

- ShadowBot-side call path is known:
  - generated input file
  - called `run.bat` or `runner.py`
  - read `runner_{run_id}.json`
- User checked the real business target or accepted output sample.
- External writes, deletes, or overwrites were explicitly authorized when involved.

## 6. Recovery State

- Project Gate Controller, Trellis, Git/PR, and runner facts are sufficient to recover without chat or Base.
- `session_auto_commit: false` is explicitly active in `.trellis/config.yaml`.
- The final Task summary names remaining risk and evidence.
- Migration or recovery events are labeled honestly rather than backdated as historical Gate closes.

## 7. Optional Base Projection

When a management Base is configured, project only high-value accepted facts. Skip this section for a deliberately local-only project. Base is not a Gate or Task writer.

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
- authoritative source references

## 8. Close Decision

Use one of three conclusions:

- `ready`: all required evidence is present and `archive-check` passed; closure can proceed after any required authorization.
- `needs_user_review`: evidence exists, but the user must confirm business acceptance, write authorization, commit, archive, or Base update.
- `blocked`: required evidence is missing or failed; name the blocker and the smallest next action.
