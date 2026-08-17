# Stage 05 — Codex-first local CLI MVP

## Status and scope

Stage 05 implements the approved Stage 01–04 contracts as an offline-first
local CLI. The implementation is a reviewable vertical slice, not release or
qualification evidence.

The product slice includes:

- frozen workspace, inspection, semantic-disclosure, and modification scope;
- complete supported-source inventory with ignored, shadowed, truncated,
  missing, unreadable, and excluded records retained;
- defensive parsing and qualifier-preserving normalization;
- reviewed Codex profile gates for instruction discovery, project trust,
  configuration precedence, Skill discovery and metadata, references, and
  attributable budget rules;
- deterministic checks, evidence lineage, local adjudication, stable IDs,
  deduplication, grouping, partial-result semantics, and reproducibility
  metadata;
- one versioned, sealed result graph projected to terminal, Markdown, JSON,
  and CI;
- a Stage 04 suite validator and runner.

Static evidence never becomes a claim about runtime selection or causality.
The check state, substantive label, and runtime-validation qualifier remain
three independent axes in the physical result schema and sealing invariants.

## Technology selection

The MVP uses Python 3.12 and the Python standard library at runtime. This keeps
the local scan deterministic and network-independent while providing built-in
TOML parsing, bounded filesystem access, canonical JSON, and cross-platform CLI
packaging. `setuptools` builds the package and `pytest` is the development test
runner; neither is imported by the product runtime.

“Offline-first” names this deterministic safety floor; it does not make the
intended product purely script-based. Model reasoning remains an optional layer
for semantic comparisons, with exact disclosure consent and local final
adjudication. That production semantic bridge is proposed for Stage 06 and is
not exposed by this CLI slice.

The package publishes the `agent-doctor` console command through
`pyproject.toml`. The product result schema is
`src/agent_doctor/data/schema/result.schema.json`.

## Install and run

From the repository root:

```sh
python3 -m pip install -e .
agent-doctor scan .
```

Useful projections:

```sh
agent-doctor scan . --format terminal
agent-doctor scan . --format markdown --output agent-doctor-report.md
agent-doctor scan . --format json --output agent-doctor-result.json
agent-doctor scan . --format ci --fail-on high
```

Project configuration is trust-gated. Supply `--project-trust trusted` only
after independently confirming the Codex project trust state. The default is
`unknown`, which preserves the configuration source but abstains where its
effectiveness is decisive. User and system sources are excluded unless
`--include-user` or `--include-system` is selected.

`--include-user` also inventories locally observed `~/.codex/skills` artifacts
and manifest-declared Skills under `~/.codex/plugins/cache`. These paths are
useful evidence for the ChatGPT desktop/Codex installation on the current
machine, but they are not documented local discovery roots in the selected
official profile. Their `effective_scope.state` is therefore `unknown`, their
provenance says runtime selection is unobserved, and their presence produces an
applicability abstention plus `complete_with_gaps`. Cached plugin versions never
become active duplicate-installation findings merely because their files exist.
The documented `$HOME/.agents/skills` behavior remains independently modeled as
applicable.

CI policies are evaluated only after schema and sealing validation. Process
exit codes are:

| Code | Meaning |
| ---: | --- |
| `0` | Valid result and CI policy satisfied, or a non-CI projection completed |
| `2` | Valid sealed result exceeded the configured CI policy threshold |
| `3` | Execution, schema, required-coverage, profile, runner, or output failure |
| `64` | Invalid CLI usage |

Threshold evaluation never removes below-threshold cases from the durable
result graph.

## Codex platform profile

The materialized profile is
`src/agent_doctor/data/profiles/codex-docs-2026-08-17.json`. It is limited to
reviewed assertions attributable to official OpenAI documentation for
`AGENTS.md`, configuration precedence/trust, and Skills. Unknown, stale,
incompatible, or non-Codex profiles cannot support version-dependent findings.

The profile is a documentation snapshot, not a claim that every installed
Codex client has identical behavior. Its compatibility gate requires that the
selected environment match the documented snapshot.

## Semantic and repair boundaries

Semantic analysis is optional in the approved architecture and is not exposed
by this product CLI slice. The Stage 04 golden harness has a test-only local
scripted adapter. It requires the exact synthetic fixture consent string,
creates a provider/model/purpose/content/exclusion disclosure manifest,
minimizes excerpts, excludes secrets and scripts, validates cited responses,
keeps model-origin evidence `inferred`, disables cross-run caching, and leaves
final adjudication local. It has no network adapter or credentials.

Repair is proposal/manual-only. Findings may include bounded manual actions,
all with `authority: none`. There is no apply or rollback command. The product
therefore does not claim the authorization, precondition, race-safety,
prior-state, verification, at-most-once, change-record, or rollback guarantees
required for automatic repair.

A sealed finding can be converted into a non-executable review artifact:

```sh
agent-doctor propose agent-doctor-result.json --case case-0123456789abcdef01234567
```

The artifact has an exact manual preview and source revisions but always has
`authority: none`, an empty executable-operation list, and unsupported automatic
rollback. It does not convert analysis or model consent into write permission.

## Stage 04 runner

Validate and run the materialized suites with:

```sh
agent-doctor spec validate test-spec/fixtures/golden-v0.1.json
agent-doctor spec run test-spec/fixtures/golden-v0.1.json --repetitions 3
agent-doctor spec run test-spec/scenarios/stage-04-catalog-v0.1.json
```

`--require-all` converts any unsupported scenario into an execution/evidence
failure. Without it, unsupported cases remain visible and unscored.

Current implementation coverage is:

- G-001–G-020: all twenty reviewed golden cases execute from synthetic inputs,
  seal a result, validate output parity, and repeat canonically three times;
- expanded catalog: 83 scenarios in the selected deterministic/output/privacy
  slice execute; 49 remain explicitly unsupported (18 optional semantic
  provider scenarios, 30 automatic-repair/rollback scenarios, and one
  repair-concurrency capability scenario).

The expanded catalog remains marked `draft` by Stage 04. These are normative
contract regressions only. No holdout sampling, independent labeling,
usefulness study, calibration run, performance qualification, or release gate
measurement has occurred, so no PRD accuracy, usefulness, calibration, or
release target is claimed.

## Development verification

```sh
pytest -q
```

Tests cover canonicalization, schemas and invariants, parsing and byte/display
spans, reference scope and symlinks, privacy, profile compatibility, frozen
scope, full pipeline sealing, deterministic identities, renderers, CI failure
semantics, the twenty goldens, the applicable expanded catalog, and CLI output.

## Repository orchestration and continuous review

The repository now includes a project Skill at
`.agents/skills/agent-doctor/SKILL.md`. It lets Codex run and explain the safe
terminal projection, while explicitly refusing to reinterpret static evidence,
read undisclosed personal Skill bodies as product evidence, or apply repairs.
It is an orchestration/explanation layer, not the missing production semantic
adapter.

`make check` is the stable local gate. GitHub Actions repeats unit tests across
supported Python versions, type checking, Stage 04 contract runs, a
repository-only CI scan, and package smoke testing on pull requests, `main`,
weekly schedule, and manual dispatch. An optional same-repository Codex review
workflow is disabled by default and remains advisory/read-only after explicit
repository configuration. Hosted workflows never inventory a developer's user
home.
