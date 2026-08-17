# Agent Doctor Stage 04 test artifacts

This directory contains Stage 04 specification data and the separate Stage 06
model-routing contract. It does not contain the test runner or Agent Doctor
product implementation.

- `schema/scenario-suite.schema.json` is the versioned contract for scenario
  suites. The test-only `not_applicable` diagnostic sentinel prevents repair,
  renderer, privacy, and other non-diagnostic contract tests from inventing a
  product `pass`, `finding`, or other check state. It must never appear in an
  Agent Doctor result.
- `fixtures/golden-v0.1.json` materializes Stage 02 examples G-001 through
  G-020 as synthetic virtual files, generated inventory, profiles, policies,
  and fault events. A future runner may materialize each case in an isolated
  temporary root.
- `scenarios/stage-04-catalog-v0.1.json` specifies the expanded component,
  integration, adversarial, metamorphic, repair-safety, and qualification
  scenarios required before release. The current local runner executes all 18
  semantic contract scenarios as well as the deterministic slice (101 total);
  31 repair mutation/concurrency scenarios remain explicitly unsupported.
- `traceability.csv` maps every required PRD, acceptance, taxonomy, golden,
  architecture-decision, component, and component-contract identifier to
  scenarios and gates.

Stage 06 preparation adds a separate, non-qualification routing contract:

- `schema/model-routing-suite.schema.json` validates the MR scenario format;
- `scenarios/stage-06-model-routing-v0.1.json` covers reviewed defaults,
  account availability, user pins, effort compatibility, qualification,
  profile freshness, and explicit semantic capability tiers; and
- `agent-doctor model spec --summary` executes the retained MR cases locally.

Passing the MR suite proves routing-contract behavior only. It does not qualify
a provider/model for semantic diagnosis.

Likewise, passing the 18 S-SEM contract cases proves lifecycle, privacy,
two-pass panel, citation, abstention, recommendation-boundary, and provenance
behavior only. It is not the independent holdout measurement required for an
accuracy, usefulness, calibration, or release claim.

English titles, inputs, and expectations are canonical. Chinese documentation
is a complete review copy, not a second active fixture corpus. Fixture contents
are synthetic and must not be replaced with production, customer, or personal
data.
