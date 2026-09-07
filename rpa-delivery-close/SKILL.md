---
name: rpa-delivery-close
description: Inspect and close delivery work for projects created from rpa-dev-template. Use whenever the user asks where an RPA project is, whether delivered code has drifted, confirms or corrects a G0-G5 result, reports a blocker or owner handoff, asks to recover cross-session state, requests a pre-G5 Gate amendment or post-G5 revalidation, wants to archive a Trellis Task, asks for Stage H, or requests a Feishu Base projection. Trellis is the only engineering Task authority; Project Gate Controller .project-gates/ is the only project Gate authority. Always compare the accepted Git baseline with current HEAD, run the evidence guard before Trellis archive, and never write project Gates into Task metadata or progress.md.
---

# RPA Delivery Close

Use this skill to combine project governance and engineering evidence without creating a second Task system.

```text
Project Gate Controller .project-gates/        = project G0-G5 and accepted Gate events
Trellis .trellis/      = engineering Task, plan, notes, checks, and archive
Git / PR               = code version and technical acceptance
runner / ShadowBot     = target-environment execution evidence
GitHub Issue/comments = requirement, scope changes and source-linked statements
Base                   = optional read-only management projection
```

One fact has one writer. Do not copy `current_gate` into `task.json`, Task notes, workspace journals, Base, or `.rpa_ai/handoff`.

## Read First

Read, when present:

1. `.project-gates/project.json`, its optional `accepted_baseline`, and the latest `.project-gates/gate-history.md` event.
2. Current and active Trellis Tasks, including PRD, design, implementation plan, notes, metadata, and final summary.
3. Linked Issue and PR.
4. Git status and recent commits.
5. Prefer `evidence/runs/{run_id}.summary.json`; use the private `runner_{run_id}.json`, logs, output, and ShadowBot evidence only when the summary is absent or details are explicitly needed.
6. Project contract and acceptance documents.

Use the bundled CLI for the authoritative local view:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> status
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> suggest
```

`status` and `suggest` are read-only. They combine sources but do not write a second current Task or Gate snapshot. Read `delivery_baseline.state`, `delivery_paths`, and `requires_user_review` before reporting that a project is delivered. `unaccepted_delivery_drift` or `history_diverged` means the current code is not covered by the last accepted baseline.

### Portable run evidence

The runtime template emits `evidence/runs/{run_id}.summary.json` after every run. Validate it before relying on it:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  evidence-check `
  --summary evidence/runs/{run_id}.summary.json
```

The Controller checks the closed schema, summary integrity SHA-256, exact run commit, status, and delivery code cleanliness. `valid` describes historical summary integrity; `delivery_ready` also checks current code. Schema 2 retains raw `working_tree_clean` and adds `delivery_tree_clean`; Schema 1 keeps its original stricter run-clean requirement. A successful or accepted warning run through `run.bat` remains eligible after record-only descendant commits. Current staged, unstaged, untracked delivery changes, divergent history, or any intervening code commit require validation again. Read `version_check` to identify the paths. See `references/evidence-version-policy.md` for the exact exemptions and compatibility policy. Summaries must not contain payloads, messages, traces, credentials, cookies, or full responses.

## Collaboration Bootstrap

After `rpa-project-bootstrap` creates the runnable code project, initialize Trellis with the pinned RPA Spec and then bootstrap Project Gate Controller:

```powershell
npx --yes @mindfoldhq/trellis@0.6.14 init `
  --registry gh:redballoom/rpa-trellis-spec-templates `
  --template rpa-python-shadowbot `
  --codex

python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  bootstrap `
  --project-name "项目名" `
  --initial-gate G0
```

Bootstrap is idempotent. It:

- creates or validates `.project-gates/project.json` and `.project-gates/gate-history.md`;
- creates or attaches one Trellis engineering Task without adding Gate fields;
- writes and reads back `session_auto_commit: false` in `.trellis/config.yaml`;
- ignores Trellis's `00-bootstrap-guidelines` system Task for the one-active-Task policy.

The project snapshot contract is published in `references/project-gate.schema.json`. Gate history remains append-only Markdown because it is an audit log, not a mutable snapshot.

Use `--init-trellis` only when an interactive Trellis CLI can run in the current environment. Use `--allow-minimal` only for an explicitly degraded test or recovery case.

## Gate Close

<!-- Correction: 2026-08-28 | was: Gate close ended after the project write | reason: an existing Task delivery route could remain stale -->

The canonical route is:

```text
G0 目标与边界
G1 交付规格
G2 契约与验收基线
G3 实现与技术验证
G4 目标环境验证
G5 业务验收与发布
```

Before closing a Gate:

1. Read Project Gate Controller and the relevant Trellis Task.
2. Report the completed result, evidence, remaining risk, and proposed next Gate.
3. Ask exactly: `当前 Gate 是否验收通过，并记录到 Project Gate Controller？`
4. Only after explicit acceptance, run `gate-close` with `--confirm-user-acceptance`.
5. Run `gate-close`; when the Task already has a route containing the accepted G2-G5 review, the command also records that review under `meta.delivery_route.completed_reviews`.
6. Read `ok`, `read_back`, and `delivery_route_sync` from the command result before reporting completion.

Example:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  gate-close `
  --accepted-gate G2 `
  --baseline-commit abc1234 `
  --confirm-user-acceptance `
  --reason "用户确认契约并允许开发" `
  --evidence docs/SHADOWBOT_INPUT_CONTRACT.md `
  --evidence commit:abc1234
```

The CLI rejects stale or repeated Gate closes. G0-G4 advance sequentially. Closing G5 keeps `current_gate=G5` and changes project status to `operational`. When Git is available, the command records the exact accepted commit in `project.json.accepted_baseline`; `--baseline-commit` pins an explicit commit and otherwise the command resolves `HEAD`. Old snapshots without this optional field remain readable but `status` reports that no accepted baseline is available.

The route synchronization reuses the existing Task-owned field; it never writes
`current_gate` or creates a route for a legacy Task. Interpret the result as follows:

- `updated`: the accepted review was added and read back;
- `already_completed`: the Task route already contained the review;
- `not_configured`: the optional route is absent, so the legacy Task remains compatible;
- `not_required` or `not_applicable`: this Gate is outside the configured Task route;
- `failed`: a local write or read-back failed; any subset of history, snapshot and Task may be written. Do not assume the project advanced.

### Interrupted operation recovery

Gate close, amendment and revalidation save `.project-gates/pending-operation.json`
before changing the history, project snapshot or existing Task route. This is a
temporary recovery journal, not a second Gate or Task authority. It is removed
only after all planned files match their read-back. Preserve it while pending;
it can contain full local Task metadata and must not be published as evidence.

When `ok=false` and `partial_commit=true`, inspect `status`. A pending operation
blocks further Gate writes, route changes and archive checks. Do not repeat the
Gate command or manually patch the route around the journal. Inspect recovery:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <root> operation-recover --dry-run
python <skill-dir>\scripts\rpa_collab.py --project-root <root> operation-recover --confirm-recovery
```

Run the second command only after authorization to finish that recorded operation.
It fills only missing writes, preserves the original event ID, and performs no
new Gate acceptance, Git commit, Task archive or external action. Repeating recovery
after completion is a no-op. A file that matches neither its recorded before nor
after image is a conflict: preserve all files and request reconciliation instead
of overwriting. Corrupt journals also stop recovery. Never delete a journal just
to unblock delivery.

The local OS lock excludes cooperating Controller writers and releases on process
exit; unrelated editors and Trellis do not acquire it, so avoid concurrent manual
edits during writes. This provides recoverable ordered writes, not a multi-file
filesystem transaction or a guarantee against device loss. Old interrupted
operations without a journal require evidence-based manual reconciliation; do not
invent their intended state. Bootstrap, migration, Task creation/archive and remote
services are outside this recovery transaction.

Use this completion report after a successful close:

```text
Project Gate: <accepted Gate> accepted; current_gate=<next Gate or G5>
Task route: <delivery_route_sync.status>; completed_reviews=<read-back list or n/a>
Evidence: <saved Gate evidence refs>
Accepted baseline: <commit or unavailable>
Next: <next Gate action and owner>
```

## Pre-G5 Gate Amendment

Use `gate-amendment` when an already accepted G0, G1, or G2 statement changes before the first G5 close. It appends a correction event and updates the accepted Git baseline without rewinding `current_gate` or overwriting the original close:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  gate-amendment `
  --gate G2 `
  --baseline-commit <full-or-resolvable-commit> `
  --confirm-user-acceptance `
  --reason "用户接受修订后的输入输出契约" `
  --evidence docs/SHADOWBOT_INPUT_CONTRACT.md
```

Before running it, show the previous accepted baseline, the changed contract, evidence, downstream impact, and current Gate. The command requires a non-empty reason, an existing initial close for that Gate, an exact Git commit, and explicit user acceptance. It is available only while the project is still in its first G0-G5 delivery. After G5, use `gate-revalidate` instead.

For G2, Task route synchronization reuses the existing review. `already_completed` is valid when the original G2 close already updated the route; `updated` repairs a route that was added or recovered later. Use pending-operation recovery after a partial failure, without repeating the amendment event.

## G5 Revalidation

After the first G5 close, maintenance never rewinds the project Gate. A major change may repeat G2/G3/G4/G5-type work in Trellis and append a Project Gate Controller revalidation after user acceptance:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  gate-revalidate `
  --gate G4 `
  --confirm-user-acceptance `
  --reason "目标环境迁移演练通过" `
  --evidence runner:migration_001.json
```

Revalidation is available only after the initial G5 close and never changes `current_gate`. It also refreshes `accepted_baseline` to the explicitly supplied commit or current `HEAD` when Git is available.
When the active Task has a route containing the revalidated review,
`gate-revalidate` records it in `completed_reviews` and returns the same
`delivery_route_sync` result. A partial synchronization failure means the
operation may be partially written; use pending-operation recovery without repeating the event.

## Trellis Task Facts

Trellis Tasks may store:

- goal, context, scope, and Acceptance Criteria;
- PRD, design, implementation plan, notes, blocker, and next engineering action;
- Issue, PR, commit, test, runner, and decision references;
- `meta.delivery_state`: `paused`, `blocked`, `in_review`, or `cancelled`;
- `meta.delivery_requirements`: whether PR, runner, and user acceptance are required;
- optional `meta.delivery_route`: the G2-G5 review path for this Issue-scoped
  delivery, never the project's current Gate;
- final engineering summary before archive.

The supported metadata shape is published in `references/trellis-delivery.schema.json`.

Agent-native Todo remains free for current-session steps. Do not mirror every Todo into Trellis.

## Issue-Scoped Delivery Route

Project G0-G5 and the current delivery are two separate dimensions. After the
first G5 close, a maintenance Task may begin with G2-, G3-, G4-, or G5-nature
work while `.project-gates/project.json` remains G5/operational.

`meta.delivery_route` is optional so older Tasks keep their existing behavior.
When present, validate it before relying on it:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  delivery-route-check
```

After the user confirms the route, write it through the adapter so the nested
JSON is written atomically and read back:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  delivery-route-set `
  --change-class major_change `
  --entry G2 `
  --require-review G2 `
  --require-review G3 `
  --require-review G4 `
  --require-review G5 `
  --project-revalidation G2 `
  --project-revalidation G4 `
  --project-revalidation G5 `
  --confirm-delivery-route
```

Do not use Trellis `task.py set-meta` for `delivery_route`; Trellis stores that
command's value as a string rather than a nested JSON object. The route writer
never changes Project Gate Controller. `project_revalidations` records intended
reviews only; each actual `gate-revalidate` still requires separate user
acceptance and evidence.

## Current Delivery And Archive Guard

Read [references/delivery-evidence-contract.md](references/delivery-evidence-contract.md)
when preparing G3/G4/G5 acceptance, recording review/check evidence, or archiving.
Agree the evidence sources and scope during contract confirmation; missing new fields
do not revoke old acceptance, but cannot grant new delivery clearance.

Use `delivery-check --stage G3|G4|G5|archive` to read the selected Task, local Git,
GitHub Issue/PR/reviews/checks and source-linked evidence. `archive-check` now uses
the same strict archive stage. Failed checks return exit 3; errors do not become a pass.
G3-G5 close and revalidation invoke this check before writing any Gate event.

Keep recorded review, local tests, GitHub conversation comments, formal Review and
GitHub check-runs distinct. An account or a local record is not authenticated human
authorship. A test source file or Trellis `check.jsonl` is not a passing test report.
Do not construct a passing record from an unexecuted check or an unperformed review.

For historical projects use `historical-check`: it always returns `ready=false`
and cannot authorize archive or Gate changes. Do not rewrite old acceptance or
fabricate missing commit/runner linkage. Old raw runner success remains diagnostic,
not current-delivery clearance. New checks require a portable summary and the
Task's corresponding original input file, verified against the summary input hash.

After user archive authorization, use:

```powershell
python <skill-dir>/scripts/rpa_collab.py --project-root <root> --task <task> delivery-archive --confirm-archive
```

This repeats preflight, invokes only Trellis `archive <task> --no-commit`, and reads
back the archived Task. It does not merge a PR, close an Issue, advance a Gate or
commit Git. A failed or interrupted Trellis archive needs inspection, not blind retry.
The underlying Trellis command can still be called directly; it is not itself
protected by this Controller. Never present that bypass as formal delivery clearance.

`--user-accepted` is an explicit caller assertion of the user's current acceptance
for this checked scope/version, not an authentication mechanism or permission to
archive/merge. Without it, final checks require a source-linked acceptance record.
Do not pass it based only on tests or a prior unrelated acceptance.

Read evidence results and missing items before reporting readiness. A fresh Issue
or PR is a platform fact; a historical comment saying "not archived" does not
override a newer archived Task. Missing paths may resolve to a unique archived
Task folder; ambiguous or absent artifacts stop validation.

## Migration

Older projects may contain either:

- project Gate files under `.hermes/project.json` and `.hermes/gate-history.md`;
- `task.json.meta.progress.current_gate` or Task-local `progress.md`.

Preview all legacy records without writing:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> migration-preview
```

When old `.hermes/` Gate files are present, bootstrap, Gate close, and revalidation must stop before creating a second state. After explicit migration approval, run:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  migrate-project-gates `
  --confirm-migration
```

This command moves only the two legacy Gate files into `.project-gates/`, records a storage-migration event, and preserves `.hermes/plugins/` and every other Hermes Agent file.

For Task-local Gate fields, create or verify Project Gate Controller state from evidence and append an explicit migration/recovery event after user awareness. Then remove legacy Gate fields from active Task metadata. Do not maintain a compatibility dual-writer. The retired `update_trellis_progress.py` intentionally refuses writes.

## Final Delivery

Before saying Stage H is ready, check:

- requirement and contract evidence;
- Task AC, technical checks, notes, final summary, and delivery requirements;
- Git commit and PR state;
- accepted baseline versus current HEAD, including delivery-impacting and governance-only paths;
- tests and runner result; validate `evidence_summary` and its `delivery_ready` state when present;
- ShadowBot and business acceptance;
- Project Gate close or revalidation event, when applicable;
- archive guard result;
- remaining risk and owner.

Use `references/stage-h-checklist.md` for the detailed checklist.

Before writing Gate close, Task archive, or workspace journal files, read `references/management-write-boundaries.md`. Keep `session_auto_commit: false`, finish the guarded read/write/read-back sequence first, then review the exact governance paths and create at most one explicit governance commit when the user authorized a commit. Do not mix generated Task/journal churn into the business implementation commit or obscure the business PR diff.

## Optional Base Projection

Base is optional and read-only. Derive its summary from saved Project Gate Controller, Trellis, Git/PR, runner, and Issue facts. A Base write never closes a Gate, archives a Task, closes an Issue, merges a PR, or publishes a release.

Do not sync secrets, full payloads, logs, customer rows, chat transcripts, or the complete Task tree. If Base is requested but the target record is unknown, request the Base link or record ID before claiming synchronization.

## Guardrails

- Do not mark delivery complete when required runner evidence is missing or failed.
- Do not treat an invalid, stale, dirty-commit, direct-`runner.py`, or non-success portable summary as delivery evidence.
- Do not replace user acceptance with tests alone.
- Do not write Gate state into Trellis Task metadata or `progress.md`.
- Do not put `current_gate` into `delivery_route`; the route describes only one Issue delivery.
- Do not make `delivery_route` mandatory for legacy Tasks or for `archive-check`.
- Do not write project Gate state under `.hermes/`; that namespace belongs to Hermes Agent.
- Do not change a Gate without explicit user acceptance.
- Do not report delivery as current when `status.delivery_baseline.requires_user_review=true`.
- Do not use `gate-amendment` after the first G5 close or for G3-G5; use the normal Gate or revalidation path.
- Do not silently replace an accepted contract: preserve the original close and append an amendment with the previous and new commit.
- Do not report a Gate close or revalidation as fully synchronized until both the Project Gate and `delivery_route_sync` read-backs succeed.
- Do not repeat a committed Gate operation to repair a failed Task route synchronization.
- Do not archive a Task before `archive-check` returns ready.
- Do not let Trellis auto-commit Gate, archive, or journal changes; keep management writes reviewable and separate from business code.
- Do not make Trellis, Project Gate Controller, Base, or GitHub a Python runner dependency.
- Do not push, merge, close an Issue, publish, delete, or rewrite history without explicit authorization.
