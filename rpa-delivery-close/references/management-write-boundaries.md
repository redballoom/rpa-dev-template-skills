# Management Write And Diff Boundaries

Use this reference when Gate close, Task archive, workspace journal, PR preparation, or final delivery will write governance files.

## Why

Project Gate and Trellis writes are valuable audit records, but generated file movement and journal churn can hide the business change in review. `session_auto_commit: false` makes those writes inspectable and prevents tool-driven commits from silently expanding user authorization.

## Guarded sequence

1. Finish and commit the business implementation at a stable tested commit when the user authorized a commit.
2. Run Project Gate Controller `status` and the applicable evidence/route/archive checks.
3. After explicit acceptance, write the Gate close/amendment/revalidation and read back both Project Gate and Task route state.
4. With separate archive authorization, run `delivery-archive --confirm-archive` (and explicit current-delivery user acceptance where required). It repeats the delivery preflight, invokes Trellis `--no-commit`, and reads back the archive. Then write the final workspace journal entry when required. Direct native Trellis archive is not guarded by this controller.
5. Read back the archived Task, Gate state, journal, Git status, and exact changed paths.
6. If the user authorized recording governance changes in Git, stage only the reviewed governance paths and create one focused commit such as `chore(governance): record accepted delivery`.

Do not create a commit after each Gate, archive, and journal command. If a partial Gate/route write occurs, preserve the pending-operation journal and inspect `operation-recover --dry-run`. After recovery authorization, use `operation-recover --confirm-recovery` to complete only that recorded operation. Do not bypass it with manual route updates or a repeated Gate event. Conflicts require reconciliation; postpone the governance commit until read-back is consistent and the pending journal is gone. The journal may contain full Task metadata and is not publishable evidence.

## PR diff partition

Show or review business and governance paths separately:

```text
Business implementation
  src/, core/, handlers/, schemas/, tests/, run.bat, runner.py, durable docs

Governance and generated collaboration state
  .project-gates/, .trellis/tasks/, .trellis/workspace/, generated agent assets

Runtime artifacts — never commit
  runner_*.json, input*.json, logs/, crash_snapshots/, data/temp/, private payloads
```

Preferred order:

- keep the main business commit limited to implementation, contract, tests, and durable documentation;
- use a later focused governance commit when these records belong in the same PR;
- if project policy keeps `.trellis/` local, exclude it from the PR and retain only stable evidence references;
- in the PR summary, list both path groups and make generated governance files collapsible or separately reviewable;
- never use a generated governance diff as proof that business code was reviewed.

Commit, push, PR creation, merge, Issue close, and release remain separate authorizations. Grouping management file writes does not grant any of them.
