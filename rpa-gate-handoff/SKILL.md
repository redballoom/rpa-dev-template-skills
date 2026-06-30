---
name: rpa-gate-handoff
description: Coordinate human-AI Gate handoffs for rpa-dev-template projects. Use whenever an RPA template task has stages, handoff files, Gate confirmation, milestone commits, contract review, implementation review, verification, delivery, or when the user asks how AI should collaborate without repeating workflow prompts. This skill makes AI automatically read/initialize/validate handoff, close each stage with a concise Gate summary, wait for user confirmation before advancing, and keep Git milestones clear.
---

# RPA Gate Handoff

Use this skill to keep RPA template collaboration smooth and deterministic.

The user should not need to repeatedly say "read `.rpa_ai/handoff/current.json`". That is AI's job. The user should mainly provide business intent, confirm or reject Gates, point out mistakes, and decide whether to continue.

## Read First

In the target RPA project, read:

- `.rpa_ai/workflow.template.json`
- `AGENTS.md`
- `README.md`
- `docs/OPERATION_GUIDE.md`

If present, read:

- `.rpa_ai/handoff/current.json`

Then follow `references/gate-handoff-protocol.md`.

## Default Behavior

At the start of a staged task:

1. Detect whether the current directory is an `rpa-dev-template` project.
2. If `.rpa_ai/workflow.template.json` exists, use the project's handoff tooling.
3. If no current handoff exists, initialize one for the most likely workspace:
   - bootstrap completed: `initialized`
   - new business requirement: `contract_review`
   - confirmed contract and coding: `minimal_implementation`
   - runtime checks: `runtime_verification`
   - delivery notes: `delivery`
   - post-project learning: `retrospective`
4. Validate handoff before and after stage work when possible.
5. Before replying with a Gate closing block, write the stage summary into the handoff file when the project supports `python tools\handoff.py close`.
6. Do not advance to the next Gate until the user confirms.

## Closing Every Stage

After every meaningful stage, update the project-local handoff first when supported:

```powershell
python tools\handoff.py close --status ready_for_review --decision "tasks.type=sync_orders" --artifact "docs/examples/input_sync_orders.json" --verification "python -m pytest tests/ -v: passed" --risk "等待用户确认进入下一 Gate"
python tools\handoff.py validate
```

Use one `--decision`, `--artifact`, `--verification`, or `--risk` per concrete item. Keep values concise and mirror them in the human-facing block.

Then end with a Gate closing block:

```text
Gate: contract_review
Status: ready_for_review
Completed: ...
Verified: ...
Risks: ...
Suggested next: minimal_implementation
Needs your confirmation: 是否进入下一阶段？
```

Keep it short. This block is for human steering, not a second report.

If `close` is not available, say the template appears to be older, run `validate` if possible, and still provide the Gate closing block. Do not ask the user to manually run `close` unless the agent is blocked from running local commands.

## User Confirmation

When the user confirms, then:

1. Archive or advance the handoff with `tools/handoff.py`.
2. Run validation.
3. If code/docs changed and tests or doctor pass, create a Git milestone commit when appropriate.
4. Continue into the next Gate.

If the user rejects or corrects the Gate, stay in the current Gate, update the contract or implementation, and close the Gate again.

## Commands

Use these project-local commands when available:

```powershell
python tools\handoff.py init --workspace contract_review
python tools\handoff.py close --status ready_for_review --decision "payload 字段已确认" --artifact "docs/examples/input_your_task_type.json" --verification "python tools/doctor.py: passed" --risk "等待用户确认进入下一 Gate"
python tools\handoff.py validate
python tools\handoff.py advance
python tools\handoff.py archive --label reviewed
python tools\doctor.py
python -m pytest tests\ -v
```

If the commands fail due to missing project support, report that the template may be older and continue with a manual Gate closing block.

## Milestone Commits

Make commits at clean milestones, not after every tiny edit.

Good commit points:

- workflow foundation added
- handoff tooling added
- business contract confirmed
- handler implemented and tested
- runtime verification completed
- failure fix completed
- delivery documentation completed

Never mix unrelated user changes into a milestone commit. If unrelated changes exist, explain them and commit only the files belonging to the current milestone.
