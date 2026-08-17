# Stage 06 — Model-assisted and continuous diagnosis roadmap

## Status

Proposed. This document does not override the approved Stage 01–04 contracts
and does not claim release readiness.

The reviewed model-routing foundation and its execution plan are now specified
in [Semantic diagnosis and OpenAI model routing design](stage-06-semantic-and-model-routing-design.md).
The routing foundation and local developmental Codex Desktop provider path are
implemented. Provider qualification, longitudinal baselines, and release
measurement remain incomplete.

## Objective

Complete the hybrid product: keep deterministic evidence collection and final
adjudication local, add a qualified exact-manifest semantic analysis path, and make
diagnosis repeatable over time without silently disclosing or changing a
user's Skill set.

## Milestones

### 06.1 Semantic disclosure and provider boundary

Implemented locally for the developmental Codex Desktop path; qualification
and protected live-canary evidence remain open.

- Resolve model choice through a reviewed, fresh capability profile; keep
  official recommendation, account availability, user policy, and product
  qualification independent.
- Materialize an exact disclosure manifest naming provider, model, purpose,
  minimized content handles, exclusions, retention/cache facts, and contract
  versions.
- Bind every invocation to that manifest digest; an explicit one-shot semantic
  diagnosis authorizes only its immediately generated manifest, while standalone
  prepare/invoke retains explicit digest confirmation. Provider/model/content/
  purpose changes invalidate authorization and cache keys.
- Exclude secrets and script/executable bodies, validate adapter lifecycle and
  response schema, require citations to disclosed handles, and retain every
  accepted model statement as `inferred` evidence.
- Use a deterministic bounded question plan, two blind analysts in parallel
  with canonical/reversed source order, and a third fresh-context judge. A
  judge-resolved disagreement is explicitly downgraded and can never become a
  finding or pass merely by majority voting.
- If exact inclusion/exclusion leaves fewer than two Skills, seal a
  not-applicable status with zero provider calls; do not widen the user's scope.

### 06.2 Local adjudication into the sealed graph

- Treat provider relations as hypotheses; only local taxonomy and
  counterexample rules may convert validated evidence into candidates,
  findings, passes, or abstentions.
- Apply taxonomy, counterexample, applicability, severity, confidence,
  deduplication, and grouping rules locally.
- Keep check state, substantive label, and runtime qualifier independent.
- Make provider failure a visible partial-result condition without erasing the
  deterministic graph.
- Keep recommendation kinds closed and label-compatible. Accepted suggestions
  remain `authority=none`, manual-only actions with benefit, risk, and
  verification; model output never authorizes a write.
- Project the sealed graph into a human-first report with per-Skill bounded
  health dimensions and explicit unknown/not-implemented areas.

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
- Detect official-model documentation drift automatically, but promote a new
  default only through reviewed profile changes and fresh qualification.

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

The first two conditions now have local developmental coverage, including all
18 S-SEM contracts. Qualification, longitudinal baselines, and measurement
remain open, so Stage 06 is not complete.
