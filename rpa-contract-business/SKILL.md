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
4. Draft the contract before coding.
5. Wait for user confirmation before handler implementation.
6. Implement handler only after the contract is clear.
7. Add tests and examples.
8. Run `python -m pytest tests/ -v` when possible.

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

Do not start implementation on your own. Wait for an explicit user confirmation such as "契约确认，开始实现".

## Progress Handoff

After explicit contract confirmation, hand off to `rpa-delivery-close` before implementation:

1. Run `status` / `suggest` against the local Trellis delivery task.
2. If the saved Gate is G2, present the contract evidence and record the accepted G2 Gate through `gate-close` after the user confirms it should be recorded.
3. If the saved Gate differs from the conversation, use a checkpoint or explicit recovery instead of forcing G2 closed.
4. Start implementation only after the local progress write succeeds and reads back at G3.

This handoff keeps contract approval, implementation permission, and the durable project state aligned without making Base a dependency.
