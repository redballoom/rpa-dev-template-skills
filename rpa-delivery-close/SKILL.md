---
name: rpa-delivery-close
description: Inspect and close delivery work for projects created from rpa-dev-template. Use whenever the user asks where an RPA project is, confirms a G0-G5 result, reports a blocker or owner handoff, asks to recover cross-session state, requests Gate revalidation, wants to archive a Trellis Task, asks for Stage H, or requests a Feishu Base projection. Trellis is the only engineering Task authority; Project Gate Controller .project-gates/ is the only project Gate authority. Always run the evidence guard before Trellis archive and never write project Gates into Task metadata or progress.md.
---

# RPA Delivery Close

Use this skill to combine project governance and engineering evidence without creating a second Task system.

```text
Project Gate Controller .project-gates/        = project G0-G5 and accepted Gate events
Trellis .trellis/      = engineering Task, plan, notes, checks, and archive
Git / PR               = code version and technical acceptance
runner / ShadowBot     = target-environment execution evidence
Gitea Issue            = requirement and discussion entry
Base                   = optional read-only management projection
```

One fact has one writer. Do not copy `current_gate` into `task.json`, Task notes, workspace journals, Base, or `.rpa_ai/handoff`.

## Read First

Read, when present:

1. `.project-gates/project.json` and the latest `.project-gates/gate-history.md` event.
2. Current and active Trellis Tasks, including PRD, design, implementation plan, notes, metadata, and final summary.
3. Linked Issue and PR.
4. Git status and recent commits.
5. Relevant `runner_{run_id}.json`, logs, output, and ShadowBot evidence.
6. Project contract and acceptance documents.

Use the bundled CLI for the authoritative local view:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> status
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> suggest
```

`status` and `suggest` are read-only. They combine sources but do not write a second current Task or Gate snapshot.

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
5. Read back Project Gate Controller and update only Task-owned evidence in Trellis.

Example:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  gate-close `
  --accepted-gate G2 `
  --confirm-user-acceptance `
  --reason "用户确认契约并允许开发" `
  --evidence docs/SHADOWBOT_INPUT_CONTRACT.md `
  --evidence commit:abc1234
```

The CLI rejects stale or repeated Gate closes. G0-G4 advance sequentially. Closing G5 keeps `current_gate=G5` and changes project status to `operational`.

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

Revalidation is available only after the initial G5 close and never changes `current_gate`.

## Trellis Task Facts

Trellis Tasks may store:

- goal, context, scope, and Acceptance Criteria;
- PRD, design, implementation plan, notes, blocker, and next engineering action;
- Issue, PR, commit, test, runner, and decision references;
- `meta.delivery_state`: `paused`, `blocked`, `in_review`, or `cancelled`;
- `meta.delivery_requirements`: whether PR, runner, and user acceptance are required;
- final engineering summary before archive.

The supported metadata shape is published in `references/trellis-delivery.schema.json`.

Agent-native Todo remains free for current-session steps. Do not mirror every Todo into Trellis.

## Archive Evidence Guard

Trellis `archive` is a technical operation and does not prove delivery readiness. Before calling it, run:

```powershell
python <skill-dir>\scripts\rpa_collab.py `
  --project-root <project-root> `
  --task <task-id> `
  archive-check `
  --user-accepted
```

The Task should provide:

- valid Project Gate Controller project state and explicit `session_auto_commit: false`;
- `meta.archive_evidence.acceptance_criteria` entries with accepted result and evidence references;
- `meta.archive_evidence.technical_checks` entries with passed result and evidence references;
- a Git commit that exists locally;
- `pr_url` when `meta.delivery_requirements.require_pr=true`;
- successful runner evidence when `require_runner=true`;
- explicit user acceptance when `require_user_acceptance=true`.
- a non-empty final engineering summary.

Recommended Task metadata:

```json
{
  "meta": {
    "delivery_requirements": {
      "require_pr": true,
      "require_runner": true,
      "require_user_acceptance": true
    },
    "archive_evidence": {
      "acceptance_criteria": [
        {"id": "AC1", "result": "passed", "evidence_refs": ["tests/result.txt"]}
      ],
      "technical_checks": [
        {"name": "unit tests", "result": "passed", "evidence_refs": ["tests/result.txt"]}
      ],
      "commit": "abc1234",
      "pr_url": "https://gitea.example/pr/12",
      "runner_refs": ["runner_delivery_001.json"],
      "user_acceptance": true,
      "final_summary": "Accepted implementation and target-environment result."
    }
  }
}
```

If the guard returns `ready=false`, do not call Trellis archive. Report the exact missing items and the smallest next action. A raw Trellis archive never closes a Project Gate, closes an Issue, merges a PR, or publishes a release.

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
- tests and runner result;
- ShadowBot and business acceptance;
- Project Gate close or revalidation event, when applicable;
- archive guard result;
- remaining risk and owner.

Use `references/stage-h-checklist.md` for the detailed checklist.

## Optional Base Projection

Base is optional and read-only. Derive its summary from saved Project Gate Controller, Trellis, Git/PR, runner, and Issue facts. A Base write never closes a Gate, archives a Task, closes an Issue, merges a PR, or publishes a release.

Do not sync secrets, full payloads, logs, customer rows, chat transcripts, or the complete Task tree. If Base is requested but the target record is unknown, request the Base link or record ID before claiming synchronization.

## Guardrails

- Do not mark delivery complete when required runner evidence is missing or failed.
- Do not replace user acceptance with tests alone.
- Do not write Gate state into Trellis Task metadata or `progress.md`.
- Do not write project Gate state under `.hermes/`; that namespace belongs to Hermes Agent.
- Do not change a Gate without explicit user acceptance.
- Do not archive a Task before `archive-check` returns ready.
- Do not make Trellis, Project Gate Controller, Base, or Gitea a Python runner dependency.
- Do not push, merge, close an Issue, publish, delete, or rewrite history without explicit authorization.
