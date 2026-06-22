# Gate Closing Format

Use this concise format at the end of staged work:

```text
Gate: contract_review
Status: ready_for_review
Completed: 已整理输入输出契约、异常语义和验收标准。
Verified: handoff validate 通过；尚未写代码。
Risks: 需要用户确认 payload 字段和输出文件。
Suggested next: minimal_implementation
Needs your confirmation: 是否按这个契约开始实现？
```

## Style

- Keep each line short.
- Prefer concrete file names and commands in `Verified`.
- Do not hide unverified items.
- Do not ask the user to run handoff commands manually unless the agent cannot run them.
- Do not advance automatically without confirmation.
