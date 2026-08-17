# Contributing to Agent Doctor

Agent Doctor changes must preserve the approved Stage 01–04 contracts and the
Stage 05 safety boundaries. Prefer small vertical slices that keep the CLI,
sealed graph, renderers, corpus, and documentation in sync.

## Development loop

1. Create a short-lived branch from `main`.
2. Install the development environment with
   `python3 -m pip install -e '.[dev]'`.
3. Implement the smallest coherent change and add or update tests.
4. Run `make check` and `make package`.
5. Open a pull request and complete the contract checklist.
6. Merge only after required checks and review pass.

The stable local commands are:

```sh
make test       # unit and integration tests
make typecheck  # mypy over the runtime package
make spec       # validate and run the Stage 04 suites
make audit      # repository-only sealed CI diagnostic
make check      # all source and contract gates
make package    # build source and wheel distributions
```

## Review invariants

Reviewers should reject a change that:

- collapses check state, substantive label, or runtime-validation qualifier;
- treats filesystem presence as runtime selection or causality;
- hides unknown, unsupported, unreadable, or partial coverage;
- expands discovery, inspection, semantic-disclosure, or modification scope by
  normalization or inference;
- sends content to a model without an exact disclosure manifest and consent;
- lets a model assign final authority, severity, or repair permission;
- changes a proposal into an executable repair without the complete Stage 03
  authorization, race-safety, verification, record, and rollback contract;
- turns policy-threshold failure into execution failure, or the reverse;
- claims accuracy, usefulness, calibration, or release readiness without the
  Stage 04 measurement evidence.

## Test-spec changes

Do not weaken golden expectations to accommodate an implementation. A changed
contract needs an attributable design decision, updates to the canonical
English source and review copy, traceability updates, and an executable
regression. Unsupported scenarios remain visible until the capability exists.

## Releases

CI builds reviewable artifacts but does not publish to a package registry.
Versioning, signing, and publication stay manual until the measurement and
release gates are satisfied.
