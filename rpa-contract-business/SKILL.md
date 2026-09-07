---
name: rpa-contract-business
description: Drive contract-first business implementation for projects created from rpa-dev-template. Use whenever the user brings a new RPA business requirement, asks what ShadowBot should provide, asks AI to write business logic, or needs tasks[].type/payload/output/status design before implementation. This skill should trigger before coding handlers, produce a concise contract summary, and wait for user confirmation before implementation.
---

# RPA Contract-First Business Implementation

Use this skill when a business requirement arrives in an initialized RPA Python project.

The first deliverable is not code. The first deliverable is a confirmed contract.

## Read First

Read these project files:

- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `docs/RPA_PYTHON_BOUNDARY.md`
- `docs/REQUIREMENT_TEMPLATE.md`
- relevant `docs/examples/input_*.json`

## Workflow

1. Understand the business goal and what ShadowBot already does.
2. Split responsibilities:
   - ShadowBot: UI, login, download, upload, manual confirmation, calling `run.bat`.
   - Python: deterministic data processing, validation, file output, structured status.
   - AI: Python code, tests, examples, docs.
3. Confirm all delivery requirements from the Issue, project risk, and user instruction:
   - Write all three booleans explicitly in the Trellis Task:
     `require_pr`, `require_runner`, and `require_user_acceptance`.
     Missing values are an incomplete G2 delivery contract, not implicit `false`.
   - Set `require_pr=true` when the user explicitly requires review-then-merge or
     when the change is high risk, such as auth/secrets, destructive data changes,
     deployment or runtime infrastructure, shared contract/schema changes, or a
     broad cross-module refactor. Record the branch convention (default
     `codex/<task-slug>`).
   - Otherwise set `require_pr=false`. This removes `pr_url` from archive evidence;
     it does not require direct commits to `main`. Choose branch isolation from
     project risk and repository policy.
   - RPA business delivery normally sets `require_runner=true` and
     `require_user_acceptance=true`. Set either to `false` only when it is genuinely
     inapplicable, and record the reason in the contract or Task notes.
   - Write the complete decision into the contract draft so it is confirmed
     together with the business contract.
   - Classify the Issue-scoped delivery route separately from the project Gate:
     `change_class`, `entry`, `required_reviews`, and any operational-G5
     `project_revalidations`. The route may use only G2-G5 review meanings and
     must never copy or replace `current_gate`.
   - Use G3 as the normal maintenance entry when the existing contract remains
     valid. Start at G2 when the Issue changes an input/output contract,
     compatibility policy, scope boundary, or acceptance baseline. Include G4
     when runner evidence is required and G5 when business acceptance is required.
   - Existing Tasks without `meta.delivery_route` remain valid. Do not infer and
     backfill a legacy route without user confirmation.
4. Draft the contract before coding.
5. Wait for user confirmation before handler implementation.
6. Complete Progress Handoff below, then return to the active Trellis execution flow for implementation, examples and applicable tests. Keep one Task and one implementation plan; do not start a second implementation workflow inside this skill.

## Contract Draft Format

```markdown
## 业务契约草案

### 影刀需要提供
- input_file: input_{run_id}.json
- business files:
- context fields:

### Python 任务路由
- tasks[].type:
- handler location:

### payload 字段
| 字段 | 必填 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- | --- |

### 输出
- business output:
- runner output:
- status expectation:

### 异常语义
- BusinessException:
- SystemException:
- retryable:
- fix_target:

### 交付要求
- require_pr: true | false
- require_runner: true | false
- require_user_acceptance: true | false
- working_branch:
- decision_reason:

### 本次交付路线（不改变项目 current_gate）
- change_class:
- entry: G2 | G3 | G4 | G5
- required_reviews: []
- completed_reviews: []
- project_revalidations: []
- route_reason:

### 验收
- sample input:
- expected output:
- tests:
```

## Implementation Rules

- Use `input_{run_id}.json` as the recommended input file name.
- Root `input.json` is only a single-run compatibility fallback.
- Route by `tasks[].type`, not task name.
- Read business parameters only from `task["payload"]`.
- Resolve relative paths from `context["repo_path"]`.
- Write business outputs to `data/output/` by default.
- Do not use `template_demo` as a real business route.

## Final Report

Include:

- Added or changed `tasks[].type`.
- Example `input_{run_id}.json`.
- Business output path.
- Expected `runner_{run_id}.json.status`.
- Test command and result.
- Remaining manual checks.
- Whether the contract is awaiting confirmation or implementation is complete.
- The three confirmed delivery requirements, working branch, and decision reason.
- The confirmed Issue-scoped delivery route, or that the legacy Task has no route and remains compatible.

Before implementation, require explicit contract and implementation authorization, such as "契约确认，开始实现". If the existing confirmation package already covers the current contract, route and implementation scope, reuse it rather than asking again. Ask only for missing decisions or material changes.

## Progress Handoff

After explicit contract confirmation, hand off to `rpa-delivery-close` before implementation:

1. Run `status` / `suggest` against the local Trellis delivery task.
2. Use the route authorization already included in the confirmed contract package; ask only if the route was omitted, is ambiguous or changed. Then use `delivery-route-set` from
   `rpa-delivery-close`; do not use Trellis `set-meta` for the structured object.
3. For an initial project currently at G2, check that the package explicitly accepted the G2 evidence and record it through `gate-close`; ask only if that acceptance is missing or no longer applicable;
   verify the Project Gate read-back at G3 before implementation.
4. For an operational G5 project, keep the Project Gate at G5 and proceed only
   after the confirmed delivery route is written and read back. Do not rewind it
   to the route entry.
5. If the saved Gate differs from the conversation, use an explicit recovery
   checkpoint instead of forcing G2 closed.

This handoff keeps contract approval, implementation permission, and the durable project state aligned without making Base a dependency.
