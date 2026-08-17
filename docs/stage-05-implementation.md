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
intended product purely script-based. Model reasoning is an optional Stage 06
extension for semantic comparisons, with exact disclosure consent and local
final adjudication. The Stage 05 deterministic floor remains independently
usable when that extension is disabled, unavailable, unconsented, or fails.

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

Semantic analysis remains optional. The Stage 06 extension now exposes
separate `semantic prepare`, `semantic invoke`, and `semantic finalize`
commands. Preparation calls no model and produces an exact manifest containing
the provider, model/effort, purpose, selected minimized claim handles,
exclusions, retention/cache statement, contract versions, and digest. A new
affirmative consent must name that digest. Secret-bearing sources and all
script/executable bodies are excluded.

Invocation uses the signed-in Codex Desktop account in an ephemeral empty
working directory, ignores user/project rules, requests tool/web/app disabling,
and rejects observed tool activity. It does not need an OpenAI API key.
Responses must use the closed schema and cite disclosed handles. Accepted
model statements remain `inferred`; state, independent labels, applicability
qualifiers, severity, confidence, grouping, and sealing are decided locally.
The adapter/model/prompt has not completed Stage 04 qualification, so this
developmental path supports no accuracy, calibration, usefulness, or release
claim.

The Stage 04 golden harness retains its test-only scripted provider for
deterministic contract regression. It performs no network request.

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
- at the Stage 05 boundary, 83 deterministic/output/privacy scenarios
  executed and 49 were explicitly unsupported. The later Stage 06 semantic
  slice now executes S-SEM-001–S-SEM-018 too, bringing the current catalog to
  101 executable scenarios; 31 repair mutation/concurrency scenarios remain
  unsupported.

The expanded catalog remains marked `draft` by Stage 04. These are normative
contract regressions only. No holdout sampling, independent labeling,
usefulness study, calibration run, performance qualification, or release gate
measurement has occurred, so no PRD accuracy, usefulness, calibration, or
release target is claimed.

## Stage 06 routing preparation

The repository now also contains a reviewed OpenAI model-capability profile,
an offline `agent-doctor model resolve` command, an explicit official-source
drift checker, and the retained model-routing contracts. These additions do not
replace the offline floor; they also drive the consented Codex Desktop semantic
exchange. Official recommendation, authenticated Codex availability, user
choice, and Stage 04 qualification remain separate. A successful developmental
run is not a provider qualification or an API-project availability claim.

See [the Stage 06 detailed design](stage-06-semantic-and-model-routing-design.md).

## Development verification

```sh
pytest -q
```

Tests cover canonicalization, schemas and invariants, parsing and byte/display
spans, reference scope and symlinks, privacy, profile compatibility, frozen
scope, semantic disclosure/consent/citation/authority boundaries, local
semantic adjudication, full pipeline sealing, deterministic identities,
renderers, CI failure semantics, the twenty goldens, the applicable expanded
catalog, and CLI output.

## Repository orchestration and continuous review

The repository now includes a project Skill at
`.agents/skills/agent-doctor/SKILL.md`. It lets Codex run and explain the safe
terminal projection and consented semantic sequence, while explicitly refusing
to reinterpret static evidence, read undisclosed personal Skill bodies as
product evidence, or apply repairs. It requires fresh digest-specific consent
before every provider invocation.

`make check` is the stable local gate. GitHub Actions repeats unit tests across
supported Python versions, type checking, Stage 04 contract runs, a
repository-only CI scan, and package smoke testing on pull requests, `main`,
weekly schedule, and manual dispatch. An optional same-repository Codex review
workflow is disabled by default and remains advisory/read-only after explicit
repository configuration. Hosted workflows never inventory a developer's user
home.
