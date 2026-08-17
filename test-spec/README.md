# Agent Doctor Stage 04 test artifacts

This directory contains specification data for Stage 04. It does not contain a
test runner or Agent Doctor product implementation.

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
  scenarios required before release.
- `traceability.csv` maps every required PRD, acceptance, taxonomy, golden,
  architecture-decision, component, and component-contract identifier to
  scenarios and gates.

English titles, inputs, and expectations are canonical. Chinese documentation
is a complete review copy, not a second active fixture corpus. Fixture contents
are synthetic and must not be replaced with production, customer, or personal
data.
