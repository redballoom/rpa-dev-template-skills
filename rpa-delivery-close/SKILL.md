---
name: rpa-delivery-close
description: Record local checkpoints, close Gates, and calibrate delivery for projects created from rpa-dev-template. Use whenever the user asks where an RPA project is, says planning/contract/implementation/integration/fix/acceptance work is complete, needs cross-session Trellis progress, reports a blocker or owner handoff, asks to sync Feishu Base, or asks for Stage H/archive. Always record Trellis locally first when available; treat Base as an optional management projection and never use .rpa_ai/handoff as the lifecycle authority.
---

# RPA Delivery Close

Use this skill when an RPA Python project reaches a milestone, delivery, acceptance, archive, or final calibration point.

The purpose is to prevent "done in chat" from drifting away from project facts. Local Trellis progress must remain sufficient for recovery even when Feishu Base is absent or unavailable.

## Read First

Read these project files when present:

- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`
- `docs/ACCEPTANCE_CHECKLIST.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `docs/RPA_PYTHON_BOUNDARY.md`
- relevant `docs/examples/input_*.json`

Read current evidence when present or provided by the user:

- Trellis task files such as `.trellis/tasks/<task>/task.json`, `prd.md`, `design.md`, `implement.md`, and archive or journal notes
- task-local `progress.md` and `task.json.meta.progress`
- installed `.trellis/spec/guides/local-progress-tracking.md`, when present
- `runner_{run_id}.json`
- `logs/run_{run_id}.log`
- `crash_snapshots/crash_{run_id}.json`
- business output files under `data/output/`
- Git status, recent commits, and relevant diff
- Base project or milestone records if the user provides a Base link, token, table, record, or asks for Base sync

If `.rpa_ai/handoff/current.json` exists, treat it as legacy context only. Do not use it as the lifecycle authority for new harness-independent projects unless the user explicitly says this is a legacy Gate/handoff project.

## Four Modes

Use checkpoint mode when meaningful work has progressed but the Gate is not ready to close, when work becomes blocked, when the next owner changes, or before ending an unfinished session.

Map clear business activity to the canonical Gate when reporting: requirement alignment is G0, planning is G1, contract approval is G2, implementation is G3, real integration is G4, and business acceptance/archive is G5. If project files are unavailable, label this as the proposed Gate pending snapshot verification instead of reporting it as unknown. Never overwrite a different saved Gate based only on chat context.

Use Gate close mode when one important point appears complete and needs human acceptance before moving on.

Examples:

- PRD or plan is ready for review.
- The user confirms the contract and allows implementation.
- A key implementation commit is ready.
- A runner or ShadowBot integration result is known.
- A fix loop reaches a verified conclusion.

Use final delivery mode when the user says business acceptance passed, asks to archive, or asks to complete Stage H.

Use recovery mode when local progress is missing or conflicts with verified Trellis, Git, runner, or archive facts. Recovery records the correction explicitly instead of fabricating skipped Gate closes.

Checkpoint mode updates the current local snapshot and appends one task-local checkpoint. Gate close mode asks for acceptance, then records one accepted local checkpoint and advances the Gate. Recovery mode calibrates stale facts with an explicit history entry. Final delivery mode calibrates all evidence groups before archive. Base synchronization is optional in every mode.

## Mandatory Gate Close Prompt

Whenever a Gate or high-value milestone appears complete, do not silently continue to the next Gate. End the report with an explicit local decision point:

```text
当前 Gate 是否验收通过，并记录到 Trellis？
```

When a management Base is configured, add:

```text
是否同时同步到飞书 Base？
```

Use this pattern:

1. Summarize the Gate result and evidence.
2. Say what local checkpoint is ready to write and which Gate will be current afterward.
3. Ask the user to confirm local acceptance; ask about Base only when configured.
4. After confirmation, update and read back local Trellis progress first.
5. When authorized and configured, write the Base milestone and update project `当前Gate` / `下一步建议`.

If the user requested Base sync and the target project record is unknown, ask for it before claiming the Base projection is current:

```text
我可以准备本次 Base 摘要，但还缺项目管理 Base 的项目记录链接或 record_id。
```

Do not block local Gate closure only because no Base is configured. Do not claim Base sync when it was expected but skipped.

## Local Progress Contract

When Trellis is present, use `task.json.meta.progress` as the current snapshot and task-local `progress.md` as append-only checkpoint history. Keep the canonical Gate route at G0-G5 and keep blockers separate from the Gate.

Prefer the bundled guard CLI before deciding what to write:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> status
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> suggest
```

`status` and `suggest` are read-only. Use them at the start of a new session, before a Gate transition, before final delivery, and whenever chat history and local files may disagree. Treat the result as a fact check, not as automatic permission to advance. If the CLI reports lifecycle drift, use an explicit `recovery` calibration after explaining the evidence; do not invent missing historical Gate closes.

Use the guard CLI for normal Gate-local checkpoints so task selection and write-back use the same resolved delivery task:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> checkpoint `
  --current-work "实现业务handler" `
  --latest-checkpoint "相关测试通过" `
  --next-action "执行runner dry-run" `
  --next-owner agent `
  --evidence "tests/test_handler.py"
```

Use `recovery` for an explicit historical calibration, including completed or archived tasks:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> recovery `
  --gate G5 `
  --current-work "历史交付状态校准" `
  --latest-checkpoint "归档项目已无后续本地动作" `
  --next-action "无后续本地动作" `
  --next-owner none `
  --evidence "commit:abc1234"
```

When Trellis has its own setup task such as `00-bootstrap-guidelines`, the guard CLI should prefer the only active task with `task.json.meta.progress.current_gate`. Pass `--task` only when more than one delivery task has local progress.

For a project that has already been created by `rpa-project-bootstrap` but has not entered local collaboration tracking, use the collaboration bootstrap wrapper:

```powershell
trellis init `
  --registry gh:redballoom/rpa-trellis-spec-templates/marketplace `
  --template rpa-python-shadowbot `
  --codex

python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> bootstrap `
  --project-name "项目名" `
  --initial-gate G0 `
  --evidence "AGENTS.md" `
  --evidence "docs/OPERATION_GUIDE.md"
```

`rpa_collab.py bootstrap` requires a full Trellis workspace by default, especially `.trellis/spec`. If the workspace has not been initialized, pass `--init-trellis` with the Trellis command details or run `trellis init` first. Do not silently create a task-only `.trellis` directory for normal projects.

This command creates or recognizes one delivery task, writes the initial local progress snapshot only when missing, and reads back `status` / `suggest`. It is intentionally idempotent: if `task.json.meta.progress` already exists, preserve it instead of overwriting the current Gate.

Use the bundled writer directly only when diagnosing the guard CLI or maintaining low-level integrations:

```powershell
python <skill-dir>\scripts\update_trellis_progress.py `
  --project-root <project-root> `
  --task <task-id-or-path> `
  --kind checkpoint `
  --gate G3 `
  --current-work "实现业务handler" `
  --latest-checkpoint "相关测试通过" `
  --next-action "执行runner dry-run" `
  --next-owner agent `
  --evidence "tests/test_handler.py"
```

For an accepted Gate, use `--kind gate_close --accepted-gate G2 --gate G3`. The script validates sequential advancement, preserves existing `meta`, appends an idempotent checkpoint, and supports `--dry-run`.

A normal checkpoint must keep the saved current Gate. A Gate close must accept the saved current Gate and advance sequentially. This prevents a progress update from silently skipping work.

Use `--kind recovery` only for explicit after-the-fact calibration. Describe the correction honestly; do not fabricate historical Gate events.

For the common accepted-Gate path, use the guard CLI wrapper:

```powershell
python <skill-dir>\scripts\rpa_collab.py --project-root <project-root> gate-close `
  --accepted-gate G2 `
  --current-work "G2 契约已验收" `
  --latest-checkpoint "用户确认契约并允许开发" `
  --next-action "进入 G3 开发实现" `
  --next-owner agent `
  --evidence "docs/SHADOWBOT_INPUT_CONTRACT.md"
```

For G5 final calibration after user acceptance, use `finish`. It requires saved `current_gate=G5`, writes a final snapshot with `next_owner=none`, marks the task completed, and reads the status back so task lifecycle and progress do not drift apart.

## Delivery Readiness

Before saying the project is delivered, check seven evidence groups:

1. Requirement and contract:
   - The business goal, input, output, exception semantics, and acceptance criteria are documented.
   - ShadowBot and Python responsibilities are clear.
2. Implementation:
   - The relevant handler or service exists.
   - Tests or a documented manual verification path cover the accepted behavior.
3. Runtime:
   - `runner_{run_id}.json` exists for the accepted run, or the user has provided equivalent evidence.
   - The status is `success` or an accepted `warning`.
   - Any `pending_fix`, `fatal`, or unresolved `retryable_error` is handled before closure.
4. ShadowBot and business validation:
   - ShadowBot called `run.bat` or `runner.py` with the expected input.
   - The user checked the real business output or target system.
5. Git:
   - The delivery-relevant changes are committed or there is a clear pending commit plan.
   - Runtime artifacts, logs, real inputs, and secrets are not staged.
6. Local progress:
   - Current Gate, current work, latest checkpoint, next action, owner, blocker, and evidence are saved in Trellis when available.
   - The task-local checkpoint history reflects the accepted decisions.
7. Optional management summary:
   - When Base is configured, the five high-value project events are prepared or synced:
     `PRD 待确认`, `允许开发`, `关键 Git 提交`, `联调结论/问题边界`, `业务验收结果`.

Use `references/stage-h-checklist.md` as the detailed checklist when the user asks for a formal Stage H close.

## Workflow

1. Identify the project, Trellis task, accepted run, and optional Base project record.
2. Run or emulate the read-only `rpa_collab.py status` / `suggest` check before deciding the write mode.
3. Identify checkpoint, Gate close, recovery, or final delivery mode from local facts and user statements.
4. Build an evidence map:
   - PRD or requirement source
   - contract or input example
   - implementation files
   - test command and result
   - runner evidence
   - ShadowBot or user acceptance evidence
   - Git commit or pending commit plan
   - Base milestone status
5. Report blockers before editing, syncing, or archiving anything.
6. In checkpoint mode:
   - update local Trellis progress without advancing the Gate;
   - record blocker and next owner when relevant;
   - do not create Base noise for every small checkpoint.
7. In Gate close mode:
   - ask the mandatory local Gate close prompt before moving on;
   - after acceptance, update and read back local Trellis progress;
   - prepare one matching Base event only when Base sync is configured and authorized;
   - do not archive the whole task unless the user asked for final closure.
8. In recovery mode:
   - state which saved facts are stale and which evidence proves the correction;
   - write one explicit recovery checkpoint rather than pretending skipped Gate closes occurred;
   - read back status and continue from the calibrated state.
9. In final delivery mode:
   - update delivery notes, Trellis task metadata, or project docs when appropriate;
   - confirm local progress and archive evidence are consistent;
   - confirm Base summaries only when Base is configured;
   - recommend archive only after user acceptance is clear.
10. Write to Base only when the user has provided the target Base context and the active environment has a suitable Base tool.
11. Recommend a Git milestone commit when files changed. Do not push, merge, delete history, or publish externally without explicit user approval.
12. Finish with a compact checkpoint, Gate close, recovery, or Stage H report.

## Optional Base Projection Rule

Base is an optional management cockpit, not the development workspace. Derive it from the accepted local checkpoint and sync only concise, desensitized summaries.

Do sync:

- event title
- project id or linked project
- Trellis task id, if available
- event type
- short summary
- decision or blocker
- commit hash
- run_id
- artifact references
- acceptance result
- idempotency key

Do not sync:

- secrets or tokens
- full payloads
- complete logs
- customer-sensitive rows
- chat transcript
- complete Trellis task tree
- local private machine details not needed for management

## Stage H Report Format

```markdown
## Stage H 交付校准

### 结论
- 状态: ready / blocked / needs_user_review
- 是否可宣称交付完成:

### 已核对证据
- 需求与契约:
- Trellis / Harness:
- Git:
- 测试:
- runner:
- 影刀 / 业务验收:
- 本地进度:
- Base 摘要（如配置）:

### 缺口或风险
-

### 已更新或建议更新
- Trellis:
- 文档:
- Base:
- Git:

### 下一步
-
```

## Checkpoint And Gate Report Format

```markdown
## 本地进度检查点

### 当前快照
- 当前Gate:
- 当前工作:
- 最近检查点:
- 下一步:
- 下一责任方:
- 是否阻塞:

### 证据
- Trellis / Harness:
- Git:
- runner:
- 影刀 / 业务:
- Base:

### 本地记录
- task.json:
- progress.md:
- checkpoint_id:

### Base 摘要（如配置）
- 标题:
- 摘要:
- 待确认事项:
- commit:
- run_id:
- 幂等键:

### 下一步
-
```

## Guardrails

- Do not mark delivery complete when runner evidence is missing or failed.
- Do not replace user acceptance with tests alone.
- Do not move to the next Gate without asking whether the current Gate is accepted and should be recorded locally.
- Do not require Base for a deliberately local-only project.
- Do not make Trellis, Base, or any Harness a runtime dependency of `run.bat`, `runner.py`, or handlers.
- Do not treat `.rpa_ai/handoff/current.json` as authoritative for new harness-independent projects.
- Do not upload real business data, payloads, logs, secrets, or customer records to Base.
- Do not push, merge, delete, or publish without explicit user approval.
