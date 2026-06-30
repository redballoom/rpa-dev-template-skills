# RPA Dev Template Skills

Portable AI skills for working with the remote `rpa-dev-template`.

These skills are designed to work on any machine where the agent can access Git, Python, and the target repository. They avoid local absolute paths and should be installed as reusable agent skills.

## Skills

| Skill | Purpose |
| --- | --- |
| `rpa-gate-handoff` | Coordinate Gate handoff, user confirmation, validation, and milestone commits |
| `rpa-project-bootstrap` | Initialize a clean RPA Python project from the remote template |
| `rpa-contract-business` | Drive contract-first business onboarding before writing handlers |
| `rpa-fix-loop` | Diagnose and repair failed RPA/Python runs |

## Recommended Flow

1. Install these skills in the agent environment.
2. Ask the agent to initialize a project:

```text
给我初始化 RPA 项目，项目地址是 C:\CodePJ\Demo，项目名称是 Demo
```

3. Discuss the business requirement with the agent.
4. Use `rpa-contract-business` to design `input_{run_id}.json`, `tasks[].type`, `payload`, outputs, exceptions, and tests.
5. Confirm the contract before code implementation.
6. Use `rpa-fix-loop` when a run fails.

## Human-AI Collaboration

The user should not need to repeatedly say:

```text
请读取 .rpa_ai/handoff/current.json，判断当前 Gate。
```

That is agent behavior. When the template supports `.rpa_ai/workflow.template.json` and `tools/handoff.py`, the skills should make the agent:

1. Read or initialize handoff automatically.
2. Complete the current Gate.
3. Validate handoff and relevant checks.
4. Write Gate decisions, artifacts, verification, and risks into handoff with `tools/handoff.py close` when supported.
5. End with a concise Gate closing block that mirrors the handoff file.
6. Wait for user confirmation before advancing.
7. Create a Git milestone commit after verified stage work when appropriate.

The user mainly provides business intent, confirms or rejects Gates, points out mistakes, and decides whether to continue.

## Template Repository

Default template URL:

```text
https://github.com/redballoom/rpa-dev-template.git
```

The bootstrap script also accepts `--template-url` if another source is needed. Use the SSH URL only on machines that already have GitHub SSH keys configured:

```text
git@github.com:redballoom/rpa-dev-template.git
```

## Install Notes

The exact install command depends on your agent runtime. For Codex-style skill installation, install this repository as a skill source, then verify that the skill names appear in the available skills list.
