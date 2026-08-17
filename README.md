# Agent Doctor

Agent Doctor is a Codex-first, offline-first diagnostic system for Skill and
agent-configuration quality. It combines a deterministic local engine with a
model-assisted review layer while keeping evidence, authority, and privacy
boundaries explicit.

Stage 05 now provides a working Python 3.12 CLI, a sealed result graph, four
output projections, the executable Stage 04 corpus, and proposal/manual-only
repair guidance. Stage 06 now adds an opt-in Codex Desktop semantic exchange:
exact minimized disclosure, digest-bound consent, isolated analyst and critic
turns, closed citations, constrained manual recommendations, local final
adjudication, and the same sealed result graph. This path is developmental and
unqualified; longitudinal comparison and measured qualification remain roadmap
work.

## What “offline-first” means

Offline-first does **not** mean “the product must be only scripts” or “a model
is never useful.” It means the safe base layer can inventory, parse, resolve,
and preserve evidence without a network call. A model can then reason over an
explicitly disclosed, minimized evidence set, while a local adjudicator retains
the final say.

```mermaid
flowchart LR
    A["Local deterministic engine"] --> B["Sealed evidence graph"]
    B --> C["Human terminal / Markdown / JSON / CI"]
    B --> D["Codex explanation layer"]
    E["Consented Codex analyst"] --> F["Fresh-context critic"]
    F --> G["Validated inferred evidence"]
    G --> B
```

The repository-level Agent Doctor Skill runs the deterministic summary and,
only after an exact disclosure manifest is approved, can orchestrate semantic
prepare, invoke, and finalize. It never treats model output as authority:
citations are validated, evidence remains inferred, and local rules decide the
diagnostic axes and whether a bounded recommendation is compatible. The critic
sees reversed source order and actively searches for a counterexample; model
agreement still does not become proof. Signed-in Codex Desktop use does not
require an OpenAI API key; provider retention remains governed by the user's
account terms.

## Quick start

```sh
python3 -m pip install -e .
agent-doctor scan .
```

Useful commands:

```sh
# A repository-only diagnostic suitable for local use or CI
agent-doctor scan . --project-trust trusted --format terminal

# Compact ID-oriented troubleshooting view
agent-doctor scan . --project-trust trusted --format debug

# Include user-level and locally observed Codex/plugin Skill inventory
# without claiming those files were selected at runtime
agent-doctor scan . --include-user --format terminal

# Validate and execute the reviewed contracts
agent-doctor spec run test-spec/fixtures/golden-v0.1.json --repetitions 3 --summary
agent-doctor spec run test-spec/scenarios/stage-04-catalog-v0.1.json --summary

# Resolve the reviewed quality-first recommendation without a model call
agent-doctor model resolve --capability semantic.reasoning_quality_first --as-of 2026-08-17

# Execute the Stage 06 routing contract (not provider qualification)
agent-doctor model spec --summary

# Prepare an exact semantic manifest without calling a model
agent-doctor semantic prepare . --include-user --source SOURCE_LOCATION

# After reviewing the package, invoke and finalize with its exact digest
agent-doctor semantic invoke semantic-package.json --consent-digest sha256:EXACT
agent-doctor semantic finalize . semantic-package.json semantic-invocation.json \
  --include-user --consent-digest sha256:EXACT
```

Install development dependencies and run the same local gate as CI:

```sh
python3 -m pip install -e '.[dev]'
make check
```

## Repository structure

```text
.agents/skills/agent-doctor/  Codex orchestration and safe explanation workflow
.github/                      CI, optional Codex review, ownership, PR policy
docs/                         Approved contracts, implementation notes, roadmap
src/agent_doctor/             Engine, bounded semantic panel, human/sealed projections
test-spec/                    Stage 04 fixtures plus Stage 06 routing contracts
tests/                        Executable unit, integration, and contract tests
```

The documentation index and status map live in [docs/README.md](docs/README.md).
Development and review rules are in [CONTRIBUTING.md](CONTRIBUTING.md), and the
automation design is in
[docs/architecture-and-automation.md](docs/architecture-and-automation.md).

## Continuous workflow

Every pull request runs tests across supported Python versions, type checking,
the Stage 04 golden and expanded suites, a repository-only Agent Doctor scan,
the model-routing contract, and a wheel build/install smoke test. The same
deterministic gate runs weekly, and Dependabot proposes dependency and Action
updates.

An optional Codex PR review workflow is included but disabled by default. It is
advisory, read-only, restricted to same-repository pull requests, and never
receives local user-home Skill content. Its model and effort have reviewed
defaults and can be overridden with repository variables. A separate weekly,
read-only workflow detects official OpenAI model-documentation drift without
an API key; it never promotes a candidate automatically. See the automation
guide for the exact secret, variables, branch-protection, and review setup.

No accuracy, usefulness, calibration, or release target is claimed until the
Stage 04 measurement protocol has produced sufficient evidence.
