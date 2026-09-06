# Evidence and delivery version

`valid` is historical summary validity. `delivery_ready` additionally requires a successful/warning `run.bat` execution with a clean delivery tree at run time, an existing exact run commit ancestral to HEAD, no intervening delivery-content commits, and no current delivery-content edits. A warning still needs business acceptance.

Schema 2 preserves raw `working_tree_clean` and adds `delivery_tree_clean`. Schema 1 remains readable and uses its recorded `working_tree_clean`; never reinterpret an old dirty run as clean. Deploy Runtime and Controller together when enabling Schema 2.

Only the following paths are exempt record files:

- `.project-gates/project.json` and `.project-gates/gate-history.md`;
- `.trellis/tasks/` and `.trellis/workspace/` records ending in `.md`, `.json`, or `.jsonl`;
- direct `evidence/runs/*.summary.json` files.

All other paths affect delivery, including `.trellis/scripts`, Spec, configuration, Skill instructions, dependencies, contracts, renamed/deleted code and unknown files. Every intervening commit is inspected, including merges; a code change followed by a revert still requires rerunning. Git failures fail closed. Git-ignored local configuration and business inputs are outside this tracked-code identity check; input hashes and target-environment review remain necessary.

Saving summary/journal/acceptance records must not invalidate a previously verified business commit. Keep `run.commit` unchanged, retain raw Git cleanliness, and use the `version_check` result rather than editing a summary to match HEAD. `status` applies the same path policy when comparing an accepted baseline.

The policy implementation is mirrored in the two standalone distributions. Meta integration tests compare the copies to prevent drift; runtime execution has no dependency on the installed Skill.
