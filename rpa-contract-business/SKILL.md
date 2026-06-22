---
name: rpa-contract-business
description: Drive contract-first business implementation for projects created from rpa-dev-template. Use whenever the user brings a new RPA business requirement, asks what ShadowBot should provide, asks AI to write business logic, or needs tasks[].type/payload/output/status design before implementation. This skill should trigger before coding handlers, initialize or validate contract_review handoff when available, close the Gate with a concise summary, and wait for user confirmation before implementation.
---

# RPA Contract-First Business Implementation

Use this skill when a business requirement arrives in an initialized RPA Python project.

The first deliverable is not code. The first deliverable is a confirmed contract.

If `rpa-gate-handoff` is available, use it. The user should not need to repeat handoff commands.

## Read First

Read these project files:

- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`
- `docs/SHADOWBOT_INPUT_CONTRACT.md`
- `docs/RPA_PYTHON_BOUNDARY.md`
- `docs/REQUIREMENT_TEMPLATE.md`
- relevant `docs/examples/input_*.json`
- `.rpa_ai/workflow.template.json` and `.rpa_ai/handoff/current.json` if present

## Workflow

1. Ensure the current Gate is `contract_review` when handoff tooling exists:
   - If no handoff exists, run `python tools\handoff.py init --workspace contract_review`.
   - Run `python tools\handoff.py validate` when possible.
2. Understand the business goal and what ShadowBot already does.
3. Split responsibilities:
   - ShadowBot: UI, login, download, upload, manual confirmation, calling `run.bat`.
   - Python: deterministic data processing, validation, file output, structured status.
   - AI: Python code, tests, examples, docs.
4. Draft the contract before coding.
5. Wait for user confirmation before handler implementation.
6. After confirmation, advance handoff to `minimal_implementation` when possible.
7. Implement handler only after the contract is clear.
8. Add tests and examples.
9. Run `python -m pytest tests/ -v` when possible.

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
- Gate closing block:
  - If contract only: `Gate: contract_review`, `Status: ready_for_review`, suggested next `minimal_implementation`.
  - If implementation completed after confirmation: close `minimal_implementation` with tests and suggested next `runtime_verification`.

Do not advance from `contract_review` to implementation on your own. Wait for an explicit user confirmation such as "契约确认，开始实现".
