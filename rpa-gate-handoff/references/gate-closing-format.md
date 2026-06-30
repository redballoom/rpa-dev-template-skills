# Gate Closing Format

Before this chat block, persist the same facts into `.rpa_ai/handoff/current.json` when supported:

```powershell
python tools\handoff.py close --status ready_for_review --decision "输入输出契约已确认" --artifact "docs/examples/input_sync_orders.json" --verification "python tools/handoff.py validate: passed" --risk "需要用户确认进入下一 Gate"
python tools\handoff.py validate
```

Then use this concise format at the end of staged work:

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
- Make the chat block match the handoff fields written by `close`.
- Do not ask the user to run handoff commands manually unless the agent cannot run them.
- Do not advance automatically without confirmation.

## Older Templates

If `python tools\handoff.py close` fails because the command is missing, keep the same chat format and briefly state that the project uses an older handoff tool. Use `python tools\handoff.py validate` if available.
