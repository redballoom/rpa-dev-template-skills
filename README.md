# RPA Dev Template Skills

Portable AI skills for working with the remote `rpa-dev-template`.

These skills are designed to work on any machine where the agent can access Git, Python, and the target repository. They avoid local absolute paths and should be installed as reusable agent skills.

## Skills

| Skill | Purpose |
| --- | --- |
| `rpa-project-bootstrap` | Initialize a clean RPA Python project from the remote template |
| `rpa-contract-business` | Drive contract-first business onboarding before writing handlers |
| `rpa-fix-loop` | Diagnose and repair failed RPA/Python runs |
| `rpa-delivery-close` | Record local Trellis checkpoints, close Gates, optionally project to Base, and calibrate final delivery evidence |

## Recommended Flow

1. Install these skills in the agent environment.
2. Ask the agent to initialize a project:

```text
给我初始化 RPA 项目，项目地址是当前目录下的 .\Demo，项目名称是 Demo
```

3. Discuss the business requirement with the agent.
4. Use `rpa-contract-business` to design `input_{run_id}.json`, `tasks[].type`, `payload`, outputs, exceptions, and tests.
5. Confirm the contract before code implementation.
6. Use `rpa-fix-loop` when a run fails.
7. Use `rpa-delivery-close` for meaningful local checkpoints, after each Gate acceptance, and after real ShadowBot integration plus business acceptance to complete Stage H. Sync Base only when configured.

## Human-AI Collaboration

The skills define stable RPA engineering actions without owning project lifecycle state. The user provides business intent, confirms the input/output contract, points out mistakes, and decides whether to continue. The active Agent or Harness owns task tracking, session memory, commits, and project-stage orchestration.

`rpa-delivery-close` is Trellis-aware, but Trellis is not a template dependency. It may read Trellis task evidence when present, and it must fall back to project docs, Git, runner output, and user acceptance when the active Harness is different.

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
