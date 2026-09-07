# Source-linked delivery evidence

Use with `delivery-check`, strict `archive-check`, and `delivery-archive`. This is
one Task's evidence contract, not a second project Gate snapshot. Missing fields in
old Tasks mean historical-only evidence until a new contract is explicitly agreed;
never backfill approval or pretend an old runner automatically binds a commit.

## Confirm at the existing contract confirmation

`meta.delivery_requirements` retains its three explicit booleans. Add:

```json
{
  "delivery_contract": {
    "schema_version": 1,
    "confirmed": true,
    "scope": "Issue #3: SWS synchronization only; preserve accepted Wenda behavior",
    "issue_url": "https://github.com/yfleCodeRepo/example/issues/3",
    "review_source": "recorded_review",
    "check_source": "local_checks",
    "required_checks": ["pytest", "doctor"]
  }
}
```

`confirmed` records the actual prior confirmation; it does not manufacture it.
Keep the scope identical in evidence records. A changed scope needs explicit
contract agreement and evidence for that scope. Only github.com is supported;
the Issue repository must match local `origin`. A closed Issue may still be valid
historical context; closure is not delivery proof. New organizations are selected
by repository URLs, not hardcoded credentials or an implicit write authorization.

- `recorded_review`: local source-linked review record or a GitHub conversation
  comment on the linked Issue/PR; explicitly label human versus Agent declaration.
- `github_review`: a current-head formal APPROVED review by an account other than
  the PR author. Account identity alone does not prove human or independent Agent
  authorship. Outstanding CHANGES_REQUESTED blocks both modes.
- `local_checks`: named source-linked execution records and actual output artifacts.
- `github_checks`: every declared name must have completed/success check-runs on
  the checked SHA. Missing, pending, skipped, neutral or failed is not success.
  Legacy commit-status contexts are not implemented; do not silently treat them
  as successful check-runs. API/authentication/pagination failures stop clearance.

Do not require GitHub CI when the confirmed contract selects local checks. A local
report remains an attestation of execution, not independent re-execution by the guard.

## Task archive_evidence additions

Retain AC, technical_checks, final_summary and PR/runner references. `commit` must
be an exact SHA. Add `review_ref`, `check_refs` (name to record reference), optional
`acceptance_ref`, and `runner_inputs` (summary reference to original local input).

```json
{
  "review_ref": ".trellis/tasks/example/evidence/review.json",
  "check_refs": {
    "pytest": ".trellis/tasks/example/evidence/pytest.json",
    "doctor": ".trellis/tasks/example/evidence/doctor.json"
  },
  "acceptance_ref": ".trellis/tasks/example/evidence/acceptance.json",
  "runner_refs": ["evidence/runs/run-001.summary.json"],
  "runner_inputs": {
    "evidence/runs/run-001.summary.json": "data/input/input_run-001.json"
  }
}
```

Original input may contain private data: keep it local/ignored, never publish it
to satisfy the checker. The summary hash must match the original input bytes.
Every supplied runner must be a current-delivery-ready portable summary; neither
latest-run fallback nor a raw success runner can override a failed summary.
This binds the Task's declared input to a run, not proof of every business outcome.

## Local record / GitHub comment record

```json
{
  "schema_version": 1,
  "kind": "local_check",
  "name": "pytest",
  "task_id": "example",
  "issue_url": "https://github.com/yfleCodeRepo/example/issues/3",
  "scope": "Issue #3: SWS synchronization only; preserve accepted Wenda behavior",
  "commit": "<40-character-commit>",
  "result": "passed",
  "actor_kind": "agent",
  "actor": "session-or-reviewer-identifier",
  "statement": "Executed the scoped tests; see the captured output",
  "command": ["python", "-m", "pytest", "tests", "-q"],
  "exit_code": 0,
  "artifact": {
    "path": ".trellis/tasks/example/evidence/pytest.md",
    "sha256": "<sha256-of-actual-artifact-bytes>"
  }
}
```

Review records use `kind=review`; acceptance uses `kind=user_acceptance` and
`actor_kind=human`, plus the saved actual confirmation source/transcript as artifact.
Checks require a nonempty command and numeric zero exit code. The guard never runs
commands read from these files. Do not produce a record unless the underlying
review, check or confirmation happened. Artifact hashes detect changes, not forgery.

Keep ordinary GitHub prose. When using a comment as machine-readable evidence,
append exactly one fenced block labelled `rpa-evidence` containing the same record.
The guard reads the actual comment, author and updated time through GitHub; it
does not publish a comment or assume prose saying "done" is sufficient. Records
may be written by an Agent using the user's account; report that limitation.
PR review-comments on diff lines and arbitrary external URLs are not currently
record sources; use linked Issue/PR conversation comments or local records.

## Stages and version boundaries

- G3: Task/source policy, Issue, PR when required, scoped review/check artifacts,
  exact delivery version, clean delivery files, safe configuration and valid route.
- G4: G3 plus runner/input binding when required.
- G5: G4 plus AC/final summary and scope/version-specific user acceptance.
- archive: G5 plus completed configured route and G5/operational project. A Task
  with no optional route remains valid. Trellis lifecycle and project Gate differ.

Gate G3-G5 writes run these checks first. An explicitly supplied accepted baseline
must equal the declared checked commit. Record-only local descendant commits are
allowed by the existing version policy; business/spec/tool changes require new
evidence. A PR must exist before the *new* G3 acceptance; do not retroactively
claim old late-created PRs met that rule.

PR evidence binds its head or actual merged commit. For a merged/squashed commit,
local delivery content must match the PR head; otherwise review again. A different
delivery commit needs new recorded attestations; no silent SHA rewriting. GitHub
state and local version are rechecked at the end, but the result is still a
point-in-time check, not a remote transaction or GitHub branch protection rule.

New final AC references must resolve to local artifacts, the linked Issue/PR, or
the checked commit. Use technical review/check fields for their detailed source
URLs. GitHub Actions, local test output, business readback, and user acceptance
remain different claims; the guard cannot prove a live target-table outcome from
a narrative alone. RF5 supplies real end-to-end evidence, not fabricated fixtures.

API references: https://docs.github.com/en/rest/pulls/reviews,
https://docs.github.com/en/rest/checks/runs,
https://docs.github.com/en/rest/issues/comments.
