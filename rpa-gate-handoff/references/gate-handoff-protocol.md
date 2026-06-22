# Gate Handoff Protocol

This protocol keeps human-AI RPA collaboration smooth, inspectable, and reversible.

## Responsibility Split

- Template: project facts, runtime contracts, scripts, schemas, tests.
- Skill: AI behavior, stage discipline, user confirmation, closing format.
- Handoff file: current stage state.
- Git commit: milestone snapshot.

## Start Of Work

1. Inspect project state:
   - `git status --short --branch`
   - `.rpa_ai/workflow.template.json`
   - `.rpa_ai/handoff/current.json` if present
2. Identify the current Gate from the user's request and the handoff.
3. If handoff is absent and the project supports it, initialize the right Gate.
4. Run `python tools\handoff.py validate` when a handoff exists.

Do not ask the user to repeat the handoff command. Only ask if the task cannot be safely classified.

## Gate Mapping

| User intent | Gate |
| --- | --- |
| initialize or inspect new project | `initialized` |
| discuss business requirement or input/output | `contract_review` |
| write handler or tests after contract confirmation | `minimal_implementation` |
| run end-to-end checks or inspect outputs | `runtime_verification` |
| prepare handover, usage notes, deployment guidance | `delivery` |
| summarize reusable lessons or template/skill improvements | `retrospective` |

## Gate Closing Block

End every stage with:

```text
Gate: <gate id>
Status: <draft | ready_for_review | completed | blocked>
Completed: <one short sentence>
Verified: <commands or checks>
Risks: <remaining risk or none>
Suggested next: <next gate or action>
Needs your confirmation: <yes/no and exact question>
```

Use this block even when the work is exploratory. It keeps the user in control without forcing them to remember workflow commands.

## Advancing

Only advance after explicit user confirmation such as:

- "确认，进入下一步"
- "契约确认，开始实现"
- "验收通过，进入交付"

Then run:

```powershell
python tools\handoff.py advance
python tools\handoff.py validate
```

If the project has changed and verification passed, create a Git milestone commit unless the user asked not to.

## Rejection Or Correction

If the user rejects the stage:

1. Stay in the current Gate.
2. Apply the correction.
3. Re-run relevant validation.
4. Close the Gate again.

Do not advance on ambiguous praise. "看起来可以" can be treated as a confirmation only when the next action is obvious; otherwise ask one concise confirmation question.
