# Stage 06 — Model-assisted and continuous diagnosis roadmap

## Status

Proposed. This document does not override the approved Stage 01–04 contracts
and does not claim release readiness.

## Objective

Complete the hybrid product: keep deterministic evidence collection and final
adjudication local, add a qualified consented semantic analysis path, and make
diagnosis repeatable over time without silently disclosing or changing a
user's Skill set.

## Milestones

### 06.1 Semantic disclosure and provider boundary

- Materialize an exact disclosure manifest naming provider, model, purpose,
  minimized content handles, exclusions, retention/cache facts, and contract
  versions.
- Require consent bound to that manifest digest; provider/model/content/purpose
  changes invalidate consent and cache keys.
- Exclude secrets and script/executable bodies, validate adapter lifecycle and
  response schema, require citations to disclosed handles, and retain every
  accepted model statement as `inferred` evidence.

### 06.2 Local adjudication into the sealed graph

- Convert validated model responses into candidates, never direct findings.
- Apply taxonomy, counterexample, applicability, severity, confidence,
  deduplication, and grouping rules locally.
- Keep check state, substantive label, and runtime qualifier independent.
- Make provider failure a visible partial-result condition without erasing the
  deterministic graph.

### 06.3 Longitudinal diagnostics

- Add local baseline and delta commands keyed by stable IDs and input revision
  manifests.
- Distinguish new, resolved, changed-evidence, and uncomparable cases.
- Retain baselines locally by default; export only a reviewed redacted summary.
- Support scheduled local runs without automatic repair.

### 06.4 Measurement and qualification

- Execute the Stage 04 holdout, independent-label, usefulness, calibration,
  privacy, repeatability, and performance protocols.
- Qualify each provider/model/adapter/prompt contract separately.
- Publish accuracy or release claims only after sample sufficiency and all
  absolute gates are satisfied.

### 06.5 Safe repository integration

- Run deterministic repository checks on every PR.
- Keep model code review advisory and separate from product semantic evidence.
- Allow an opt-in private runner to produce redacted deltas, but never expose a
  personal home to untrusted PR code.
- Keep repairs proposal/manual-only until the entire authorization, race-safe
  apply, verification, at-most-once record, and rollback matrix passes.

## Exit criteria

Stage 06 is complete only when the semantic path produces one valid sealed
result graph, all applicable semantic/privacy scenarios execute, provider
qualification is attributable, local baselines are reproducible, and the
Stage 04 measurement protocol—not implementation confidence—supports the
claimed quality level.
