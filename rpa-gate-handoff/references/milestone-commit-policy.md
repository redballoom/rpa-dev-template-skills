# Milestone Commit Policy

Milestone commits make exploratory work reversible.

## Commit After

- A Gate is completed and verified.
- A reusable tool or schema is added.
- A contract is confirmed and saved.
- A handler is implemented with tests.
- A failure fix is verified.
- Delivery documentation is ready.

## Do Not Commit When

- The contract is still uncertain.
- Tests or doctor checks fail.
- Runtime artifacts are present.
- Unrelated user changes would be mixed into the commit.
- The user explicitly asks not to commit.

## Commit Message Examples

```text
feat: add workflow productization foundation
feat: add handoff lifecycle tooling
feat: add contract for ad report sync
feat: implement ad report transform handler
test: verify ad report runtime flow
fix: route missing input file to rpa fix target
docs: add delivery notes for ad report sync
```
