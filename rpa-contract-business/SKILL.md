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
3. Draft the contract before coding.
4. Wait for user confirmation before handler implementation.
5. Implement handler only after the contract is clear.
6. Add tests and examples.
7. Run `python -m pytest tests/ -v` when possible.

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
- Whether the contract is awaiting confirmation or implementation is complete.

Do not start implementation on your own. Wait for an explicit user confirmation such as "契约确认，开始实现".
