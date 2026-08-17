# Agent Doctor Test Scenarios and Quality Gates

| Field | Value |
| --- | --- |
| Status | Review draft |
| Test specification version | 0.1 |
| Date | 2026-08-17 |
| Canonical language | English |
| Companion review copy | [中文](test-scenarios-and-quality-gates.zh-CN.md) |
| Governing product definition | [Product requirements](product-requirements.md) |
| Governing diagnostic contract | [Conflict taxonomy and golden examples](conflict-taxonomy-and-golden-examples.md) |
| Governing architecture | [Detailed design and architecture](detailed-design-and-architecture.md) |
| Project stage | Stage 04 — test scenarios and quality gates only |

## 1. Purpose, status, and boundaries

Stage 04 makes the approved Stage 01–03 behavior verifiable. It defines the
test strategy, versioned scenario contract, materialized golden corpus,
expanded scenario matrix, measurements, release gates, data governance,
environment controls, failure artifacts, and traceability for the Codex-first
local CLI MVP.

This stage does not implement Agent Doctor, select a test framework or CI
service, package a CLI, qualify a real provider, or claim that any product
target has been met. The materialized files under `test-spec/` are test data
and contracts, not a runner or product code.

The following remain binding:

- diagnosis is read-only by default and deterministic diagnosis is offline;
- semantic analysis is optional, disclosed, minimized, and locally
  adjudicated;
- static evidence never proves runtime Skill selection or causality;
- check state, substantive label, and validation qualifier are independent;
- unknown, withheld, disabled, or failed work cannot become `pass`;
- one sealed result graph feeds terminal, Markdown, JSON, and CI;
- every supported write has exact preview, bounded authority, stable
  preconditions, protected prior state, verification, an attributable record,
  revocation/expiry checks, at-most-once behavior, and safe rollback refusal.

### 1.1 Stage 04 assumptions

1. English Stage 01–03 documents are canonical; Chinese copies are complete
   review aids.
2. The Stage 02 examples are normative. Their materialization may add execution
   metadata but cannot weaken, relabel, or omit decisive evidence.
3. A future runner can instantiate the virtual files, generated source series,
   controlled provider responses, clocks, capabilities, and fault barriers
   defined by the fixtures.
4. Platform-dependent deterministic claims are executable only with a reviewed,
   compatible profile. Synthetic fixture profiles test contracts but do not
   qualify current Codex behavior.
5. A concrete repair type is unsupported until Stage 05 selects it and the
   complete safety matrix passes on every claimed filesystem capability profile.
6. “Reviewed” on the Stage 02 materializations means internal normative and
   materialization review. It does not mean independent qualification or
   statistical sufficiency.

### 1.2 Explicitly deferred choices

Stage 05 retains choice of test language and framework, runner layout, parser
libraries, assertion and property-test libraries, process isolation mechanism,
CI vendor, numeric process exit codes, provider/model list, prompt wording,
record/replay format, real platform profiles, concrete repair allowlist,
filesystem primitives, protected recovery storage, hash/canonicalization
algorithm, performance SLOs, and product result-schema serialization.

Deferral cannot weaken a test oracle. In particular, no framework may make
provider output authoritative, use ambient paths, hide partial coverage, or
skip mutation preconditions because a platform primitive is inconvenient.

## 2. Test principles and oracles

### 2.1 Principles

1. **Contract before implementation.** Tests assert public behavior and
   component boundaries, not private classes or a preferred code layout.
2. **One question per scoring unit.** A diagnostic scenario freezes one check,
   applicability region, and dimension. Grouping is scored separately.
3. **Exact positive and negative assertions.** Every case names allowed output
   and prohibited outcomes, including forbidden reads, writes, leaks, and
   runtime claims.
4. **Failure is typed.** Disabled/unavailable-before-start, attempted failure,
   missing decisive evidence, policy failure, and run execution failure have
   different oracles.
5. **Evidence provenance is part of correctness.** A correct label supported by
   the wrong evidence kind is a failed test.
6. **Safety uses zero-tolerance scenarios.** Authorization, disclosure,
   concurrency, rollback, and secret-exclusion failures cannot be averaged
   away by an accuracy score.
7. **Determinism is compared canonically.** Run IDs, timestamps, safe provider
   request IDs, and renderer prose may vary; stable identities, evidence
   lineage, inventory, states, labels, qualifiers, coverage, and operation
   records may not.
8. **No production data.** Qualification uses reviewed synthetic inputs and
   fake sentinel secrets only.

### 2.2 Oracle order

When sources disagree, use this order:

1. canonical PRD product behavior and acceptance criteria;
2. Stage 02 taxonomy, adjudication rules, and exact G-001–G-020 expectations;
3. Stage 03 architecture decisions, component contracts, and safety
   invariants;
4. the exact scenario oracle and compatible profile cited by the fixture;
5. canonical filesystem snapshots, provider scripts, clocks, consent/grant
   records, proposal/change records, and sealed result graph;
6. renderer projections and CI decisions derived from that graph.

A fixture that conflicts with levels 1–3 is a fixture/oracle defect; the product
must not be changed to satisfy it. Model output is never an oracle by itself.

### 2.3 Principal risks and controls

| Risk | Stage 04 control |
| --- | --- |
| Twenty examples are treated as sufficient evaluation | Separate normative golden regression from a larger independent qualification corpus and minimum sample rules. |
| Candidate or abstention hides false negatives | Score exact state separately; candidates/abstentions do not earn finding true positives. |
| Static evidence is described as runtime truth | Prohibited-outcome assertions and runtime-qualifier property tests. |
| Platform rules silently become stale | Compatibility, provenance, stale/unknown/incompatible profile cases and gates. |
| Renderer snapshots drift into independent diagnoses | Semantic parity comparison against one sealed graph. |
| Semantic tests leak evaluation content or secrets | Synthetic data, holdout isolation, manifest consent, sentinel scans, and no default cross-run cache. |
| Mutation tests damage the developer workspace | Case-local roots, controlled capabilities, snapshot manifests, and cleanup verification. |
| Race tests become flaky timing tests | Named deterministic barriers inject target changes. |
| Aggregate metrics hide class or group failures | Per-class/per-profile strata, exact-state matrix, group/member scoring, and zero-tolerance gates. |

## 3. Versioned scenario and fixture contract

The physical Stage 04 contract is
[`scenario-suite.schema.json`](../test-spec/schema/scenario-suite.schema.json).
It uses `agent-doctor-test-scenario/0.1`; changing required meaning requires a
new schema version. Published cases retain stable IDs. A decisive input or
expected-result change increments the fixture version and is reviewed as a
golden change, not silently overwritten.

Every case explicitly contains:

| Area | Required fields and meaning |
| --- | --- |
| Identity | Stable ID, title, schema/fixture version, level, polarity/kind, and test type. |
| Traceability | PRD, acceptance, taxonomy, architecture, and gate references. |
| Rule context | Platform profile, rule set, and compatible/unknown/stale/incompatible status. |
| Modes and boundaries | Deterministic, semantic, and repair modes; selected region; separate discovery, inspection, semantic-disclosure, and modification boundaries; exact consent statement. |
| Setup and input | Preconditions, synthetic virtual files and policies, precise generators, configuration, provider script, controlled clock, and scheduled faults. |
| Stimulus | Named component contract plus ordered steps. |
| Oracle | One question, decisive evidence, rationale, acceptable uncertainty, and strongest counterexample. |
| Diagnostic expectation | Exact check state, labels, qualifiers, severity/potential severity, confidence, and the applicable severity/confidence rule. |
| Evidence and coverage | Allowed evidence kinds, exact inventory statuses and inclusions/exclusions, required check families, gaps, and run outcome. |
| Outputs and mutation | Terminal/Markdown/JSON/CI assertions; proposal/apply/rollback state and exact file-write count. |
| Negative assertions | Prohibited classifications, reads, disclosures, writes, claims, or state transitions. |
| Isolation and review | Cleanup boundary and postconditions; draft/reviewed/disputed/retired status, reviewers, and date. |

`not_applicable` is a test-spec-only diagnostic sentinel for repair, renderer,
privacy, and other contract tests that do not execute a product diagnostic
check. It avoids inventing a product `pass` or `finding`. It is not part of the
Agent Doctor result schema and must never be rendered as a check state.

The schema permits virtual filesystem entries, deterministic generators, and
named fault barriers. It intentionally does not select an implementation
language, runner, storage database, hash, or assertion library.

## 4. Test layers and ownership boundaries

| Layer | Primary contracts/components under test | Main oracle and forbidden ownership |
| --- | --- | --- |
| L0 schema/invariant | Result assembler, evidence ledger, result/change records | Closed enums, three axes, lineage, multi-label and operation-state invariants. Validation may reject; it may not repair or re-adjudicate data. |
| L1 parser/normalizer | `ReadSource`, `ParseAndNormalize` | Same bytes/version produce equivalent claims and exact source spans; modality, exclusions, and original text survive. Parser does not decide semantic relations. |
| L2 discovery/resolution | `PlanScope`, `Inventory`, `ResolveReference`, `ResolveApplicability`, profile registry | Complete inventory, separate scopes, declaring-source-relative paths, versioned precedence/budget/schema rules. No guessed platform behavior or out-of-scope read. |
| L3 deterministic rules | `RunDeterministicCheck` | Observed facts plus named compatible rules produce reproducible results offline. No model calls or pass on partial prerequisites. |
| L4 semantic boundary | `BuildSemanticDisclosure`, `RunSemanticCheck`, semantic coordinator and adapter | Exact consent manifest, minimized handles, response schema/citations, inferred provenance, provider lifecycle. Provider cannot assign final state/severity or authority. |
| L5 local adjudication | `Adjudicate`, counterexample, abstention, confidence | Ordered taxonomy procedure and exact claim/region/dimension key. Adjudicator cannot erase upstream errors or upgrade inferred evidence. |
| L6 identity/grouping/output | `GroupCases`, result assembler, `Render`, `EvaluateCI` | Stable/lossless cases and groups; one result across terminal, Markdown, JSON, CI; policy failure differs from execution failure. Renderers run no checks. |
| L7 repair planning/authority | `ProposeRepair`, `ValidateAuthorization` | Reversible allowlist, exact preview/digest, target/operation/session/time/revocation scope, single-use confirmation. Selection or consent grants no authority. |
| L8 apply/verify/rollback | `ApplyProposal`, `VerifyChange`, `RollbackChange`, ledger | All-target preflight, target-local race protection, protected prior state, stop-on-failure, exact post/prior verification, at-most-once records, safe refusal. No silent replan or merge. |
| L9 privacy/trust | Scope guard, content broker, provider boundary, sinks, recovery store | No network for deterministic work; no secret/script leakage or execution; analyzed content cannot alter scanner policy or authorize writes. |
| L10 compatibility/qualification | Profiles, all version fields, environment capability matrix, full flows | Reproducible input manifests, compatible attribution, deterministic repetitions, independent ground truth, and release gates. It makes no architecture choice. |

Component tests use contract stimuli and typed values. Integration tests verify
transitions between owners. System and qualification tests verify complete
user-visible behavior without allowing downstream layers to correct an
upstream contract violation silently.

## 5. Materialized Stage 02 golden corpus

[`golden-v0.1.json`](../test-spec/fixtures/golden-v0.1.json) materializes all
twenty Stage 02 examples with virtual files, source policies, line locations,
generated inventories, profile facts, and fault events. The table below is a
preservation check, not a relabeling.

| ID | Exact expected state | Labels / qualifier | Severity; confidence | Decisive preserved boundary |
| --- | --- | --- | --- | --- |
| G-001 | `finding` | `scope_overlap`, `semantic_conflict` | high; high | Same mandatory run/do-not-run action, shared dependency-update region, no resolving precedence. |
| G-002 | `pass` | `complementarity` | info; high | Start and end requirements are jointly satisfiable. |
| G-003 | `candidate` | `scope_overlap`, `complementarity`; `runtime_validation_needed` | potential medium; medium | Static overlap and distinct contributions; routing selection remains runtime-only. |
| G-004 | `finding` | `scope_overlap`, `behavioral_redundancy` | medium; high | Same identifier and normalized content at two discovered paths; one grouped alert. |
| G-005 | `pass` | `scope_overlap`, `complementarity` | info; high | PDF extraction and arithmetic verification are distinct and composable. |
| G-006 | `pass` for active conflict | `precedence_override` | info; high | Compatible documented nested replacement leaves only JSON effective. |
| G-007 | `insufficient_evidence` | no winner | no severity; high abstention | Peer authority/order rule is absent; potential high impact is separate. |
| G-008 | `finding` | `invalid_reference` | medium; high | Mandatory declaring-file-relative target is absent. |
| G-009 | `insufficient_evidence` | no stale label | no severity; high abstention | Old mtime without a freshness/version contract proves nothing. |
| G-010 | `finding` | `stale_reference` | high; high | Resolving schema-2 target explicitly rejects required schema 3. |
| G-011 | `finding` | `invalid_reference` | medium; high | Normalized target escapes scope; outside content is never read. |
| G-012 | `finding` | `context_budget_risk` | medium; high | Compatible 100-entry rule, 112 eligible entries, and 12 observed omissions. |
| G-013 | `insufficient_evidence` | no budget label | no severity; high abstention | Visual length lacks current unit, limit, loading phase, or truncation evidence. |
| G-014 | `finding` | `configuration_risk` | medium; high | Closed compatible schema rejects `mode: sometimes` and documents ignore effect. |
| G-015 | `not_run` | none | none | Semantic mode disabled before start; deterministic results remain usable. |
| G-016 | `insufficient_evidence` | no redundancy/conflict label | no severity; high abstention | Descriptions are visible but behaviorally decisive bodies remain outside consent. |
| G-017 | `candidate` | `scope_overlap`; `runtime_validation_needed` | potential medium; medium | Identical primary-handler witnesses support a routing hypothesis, not observed misrouting. |
| G-018 | one grouped `finding` | overlap; redundancy on output; conflict on edit/question dimension | high; high | Different dimensions make the multi-label combination legal and lossless. |
| G-019 | `pass` | `no_material_relation` | info; high | Identical text has disjoint frontend/backend applicability for the selected file. |
| G-020 | `error` | none | none | Source was inventoried and the check started before read retries failed. |

Every fixture repeats its acceptable uncertainty and prohibited
misclassifications. In particular, none asserts future Skill selection,
runtime compliance, or causal effect. Promotion from this internally reviewed
materialization to an approved qualification corpus requires the independent
review in section 8.

## 6. Expanded scenario matrix

[`stage-04-catalog-v0.1.json`](../test-spec/scenarios/stage-04-catalog-v0.1.json)
contains 132 additional scenarios. Together with the twenty goldens, Stage 04
specifies 152 cases.

| Family and IDs | Required coverage |
| --- | --- |
| Schema/invariants `S-SCH-001`–`006` | Valid graph; state/label separation; invalid `not_run`/`error`; resolved-conflict prohibition; model agreement remains inferred. |
| Parser `S-PAR-001`–`005` | LF/CRLF/Unicode locations, modality, exclusions, partial malformed input and completeness. |
| Discovery `S-DIS-001`–`008` | Complete chain; ignored, shadowed, truncated, missing, unreadable; out-of-scope addition and irrelevant-order metamorphisms. |
| Scope/precedence `S-SCP-001`–`006` | Explicit/unknown precedence; empty, shared, and unknown regions; dimension-qualified interactions. |
| References `S-REF-001`–`010` | Declaring-file-relative resolution, dot normalization, lexical/symlink escape, identity swap, case profiles, supported/unsupported variables, transient I/O. |
| Profiles `S-PRO-001`–`005` | Compatible, unknown, stale, incompatible, and version-changing profiles. |
| Configuration `S-CFG-001`–`004` | Divergent duplicate identifiers under a profile rule, forward-compatible versus rejected unknown fields, documented defaults. |
| Budget `S-BUD-001`–`004` | Correct-unit exceedance, unknown allocation, stale rule, and wrong unit/loading phase. |
| Semantic `S-SEM-001`–`018` | Disabled/unavailable, post-start timeout/failure, malformed/uncited/ambiguous responses, minimization, redaction, secret/script exclusion, consent/provider/model changes, cache invalidation, model agreement, provider overreach, prompt-like content, unknown retention. |
| Adjudication `S-ADJ-001`–`008` | Counterexamples, evidence withholding, low-confidence candidate, precedence resolution, non-pass failure states, exact deduplication, non-redundant similarity, lossless grouping. |
| Outputs/CI `S-OUT-001`–`011` | Renderer parity, stable/change-sensitive IDs, lossless groups, partial results, repeatability, policy versus execution failure, renderer isolation, threshold completeness, localization. |
| Repair `S-REP-001`–`030` | Authorization absence and all target/operation/session/expiry/revocation/digest mismatches; confirmation replay; preview; unsupported repair; prior-state failure; precondition and identity races; partial apply; verification; at-most-once; safe and conflicted/partial/failed rollback; mid-run authority loss; record completeness. |
| Privacy `S-PRV-001`–`009` | Offline deterministic run, non-substitutable consents, sentinel secrets, no script execution, untrusted configuration, recovery isolation, exact disclosure, minimized outputs. |
| Compatibility/reproducibility `S-CMP-001`–`008` | Independent version attribution, unknown/stale/incompatible profiles, revision manifests, missing filesystem capabilities, controlled clock and deterministic race barriers. |

The matrix contains positive, negative, boundary, abstention, `not_run`, error,
property, metamorphic, and adversarial cases. It treats missing/unreadable
sources and operation failures as lifecycle facts, not evidence that a
configuration is valid or invalid.

## 7. Metamorphic, property-based, and adversarial properties

The following are release-relevant invariants. A property runner may generate
more examples, but generated shrinking must preserve the decisive qualifier,
scope, consent, profile, and event order.

| Property | Expected relation |
| --- | --- |
| Renderer independence | Switching terminal, Markdown, JSON, or CI cannot change diagnostic axes, stable IDs, evidence lineage, grouping, or coverage. |
| Irrelevant-order independence | Reordering sources, directory enumeration, or equivalent map fields cannot change canonical results. |
| Scope monotonicity | Adding a source outside frozen discovery/inspection scope cannot add an in-scope case or read. |
| Evidence monotonicity | Removing or withholding decisive evidence cannot produce a stronger state, severity, confidence, or evidence kind. |
| Provenance immutability | One or many models agreeing cannot convert inferred evidence into observed/derived/runtime evidence. |
| Precedence soundness | Once a compatible rule resolves a contradiction, it cannot remain an active `semantic_conflict`. |
| Failure-state soundness | `not_run`, `insufficient_evidence`, and `error` have no transition to `pass` without a new completed check. |
| Consent/authority non-expansion | Parsing, path normalization, case folding, variable expansion, or canonicalization cannot enlarge disclosure or modification authority. |
| Proposal immutability | Any target, operation, exact diff, precondition, identity, or proposal digest change requires a new preview and authority decision. |
| Apply identity | A changed source revision, canonical target identity, path, grant state, session, or time boundary blocks the affected write. |
| Rollback identity | A changed recorded post-image, identity, path, or authority blocks restoration; no automatic merge is permitted. |
| At-most-once | Replaying confirmation, apply attempt, or completed rollback returns the recorded result without a second mutation. |
| Group losslessness | Permuting or deduplicating occurrences may not delete member cases, regions, dimensions, states, or evidence locations. |
| Version sensitivity | Volatile run data cannot change stable IDs; a decisive contract/profile/claim change cannot retain an old ID silently. |

Adversarial inputs include path traversal, symlink and inode swaps, case
ambiguity, unsupported variable forms, prompt-like instructions to the
scanner/provider, secret echoes, malformed provider envelopes, digest replay,
clock jumps, revocation between operations, concurrent apply/rollback changes,
and output-destination failures.

## 8. Measurement protocol

### 8.1 Corpora and scoring units

Maintain three disjoint sets:

- **development:** visible cases for implementation and debugging;
- **normative regression:** G-001–G-020 and safety contract regressions;
- **qualification holdout:** independently reviewed cases unavailable to
  product/prompt tuning and scored only by an authorized qualification run.

The primary diagnostic scoring unit is one `(fixture revision, check ID,
question, claim set, applicability region, dimension)` interaction case. A
multi-dimension group contributes one class decision per dimension, while user
actionability is scored once per user-visible group. Files and raw alert lines
are never scoring units.

For inventory, one expected supported source occurrence and expected status is
one unit. For renderer parity, one canonical semantic field per case/group is
one unit. For repair safety, one operation attempt and each target transition
are asserted; failures are scenario pass/fail and are not averaged into
diagnostic precision.

### 8.2 Ground truth and reviewer independence

1. Two qualified reviewers label each qualification case independently, blind
   to Agent Doctor output, provider output, and each other's labels.
2. Reviewers verify full decisive content, scope, profile compatibility,
   claim modality/exclusions, region, dimension, exact state/labels/qualifier,
   severity, confidence rule, acceptable uncertainty, and prohibited outcomes.
3. A third adjudicator resolves disagreements from the canonical sources.
   Unresolved label-changing disagreement becomes explicit
   `insufficient_evidence` or keeps the case out of qualification.
4. Fixture authors, product/prompt tuners, and final reviewers must be recorded.
   A person may not be the sole ground-truth reviewer for a case they authored.
5. Ground-truth revisions create a new fixture version and retain the old
   decision history.

### 8.3 Deterministic scoring

A predicted positive is a `finding` emitted by the eligible deterministic
rule for the exact ground-truth question. Compute micro precision and recall
over scorable cases and report per-rule-family precision/recall/confusion
tables:

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
```

- A correct label on the wrong region/dimension, wrong evidence kind, or
  incompatible profile is not a TP.
- A `candidate` or `insufficient_evidence` on an expected deterministic
  finding is an FN; it does not earn partial TP credit.
- A candidate on an expected negative is not a finding FP, but it is an
  exact-state error and is reported in candidate false-alarm and answer-rate
  tables.
- A required check that is `not_run` or `error` invalidates that qualification
  run for the affected family; it is not a true negative.
- Expected abstention, `not_run`, and error cases are scored in a separate exact
  state/reason matrix and must not enter the positive/negative denominator as
  if they were ordinary negatives.

AC-2 is evaluated only after sufficient independent data exists: at least 200
scorable deterministic decisions overall and, for each shipped P0 rule family,
at least 30 positive and 30 negative/nearest-boundary decisions. The approved
set must include every claimed filesystem/profile capability and every
critical expected case. Report point estimates and 95% Wilson intervals. The
release target is at least 95% precision and 95% recall, with zero critical
false negatives. This document makes no claim that the target is currently met.

### 8.4 Semantic scoring

A semantic predicted positive is a local-adjudicator `finding` with the exact
problem label, region, and dimension. `pass` explanatory relations,
`candidate`, and `insufficient_evidence` are not positive predictions.

- A candidate on an expected finding is an FN for finding recall, while its
  candidate quality is reported separately.
- An expected candidate is correct only when the state, hypothesis, label, and
  `runtime_validation_needed` proposition match. It is not a semantic finding
  TP.
- Intentionally ambiguous cases may not be forced into `pass` or `finding`.
  Any such result is a zero-tolerance ambiguity violation regardless of
  aggregate precision.
- Expected complementarity/no-material-relation controls are negatives for
  problem finding; incorrect problem findings are FPs.
- Duplicate alerts are not extra TPs. The first correct group can score; each
  additional substantially identical group is an FP/duplicate defect.
- G-018-like cases score assessments by dimension and group losslessness
  separately.

The qualification corpus must contain at least 200 independently reviewed
semantic interaction cases, including at least 50 policy-annotated blocking
positive cases, 50 nearest-neighbor negative controls, 30 deliberate
ambiguity/abstention cases, and at least 20 positive plus 20 nearest-negative
cases for every shipped semantic class. One case may satisfy multiple declared
strata, but each scoring unit appears once in micro totals.

“Blocking” is an evaluation annotation under a frozen CI policy, not a new
taxonomy label and not automatically derived from severity. Report blocking
precision, overall precision/recall, per-class results, macro averages,
candidate rate, abstention rate, and exact-state confusion. AC-5 targets are
blocking precision at least 90%, overall precision at least 85%, and recall at
least 75%. AC-6 requires at least 80% actionability among emitted semantic
finding groups and zero forced decisions on intentional ambiguity. No target is
claimed before a sufficient holdout run exists.

### 8.5 Confidence, severity, and actionability

- Ground truth reviews severity as impact and confidence as evidence support;
  neither substitutes for the other.
- Report empirical precision and a 95% Wilson interval for high, medium, and
  low confidence problem predictions. When a bin has fewer than 30 predictions,
  mark calibration evidence insufficient rather than extrapolating.
- A release claiming calibrated confidence needs no unexplained inversion in
  which a sufficiently populated higher-confidence bin is materially less
  precise than a lower bin. The PRD sets no numeric calibration-error target,
  so Stage 04 does not invent one.
- Actionability is a blinded yes/no group-level review: evidence is adequate,
  the next step is bounded and relevant, and the user can act without trusting
  an opaque score. Reviewers record reasons and disagreements.

### 8.6 Semantic repeatability and provider qualification

Scripted providers and sanitized recordings test adapter contracts offline;
they do not establish live-model accuracy. Live-provider qualification is
optional, synthetic-only, consented, and separately identified by provider,
model, adapter, prompt contract, policy, and exact input digest.

For a live provider/model release claim, run three isolated passes over the
frozen holdout. Score each pass independently and pooled; all three must meet
the applicable point targets and zero-tolerance conditions. Report case-level
disagreement/stability rather than hiding it with majority voting. Provider or
model changes invalidate the qualification and consent/cache keys.

### 8.7 Leakage prevention and reproducibility

- Qualification case content, labels, and provider recordings are not used to
  author rules, tune prompts, choose examples, or debug before the run closes.
- Development and qualification IDs/digests are stored separately; provider
  cache is empty or precisely invalidated for qualification.
- Every score binds the fixture suite version, input revision manifest,
  product/result/taxonomy/rule/normalization/profile/grouping/semantic-contract
  versions, modes, policy, environment capability profile, and model-call
  metadata without credentials.
- Deterministic qualification repeats each case three times and compares the
  canonical result after removing only declared volatile fields.

## 9. Release-quality gates

Gate evaluation first determines whether evidence is valid. Missing fixtures,
unsealed results, a required-family error, insufficient sample size, invalid
ground truth, or broken evaluator tooling is an **execution/evidence failure**:
no policy score is asserted. A valid result below a measured target or above a
configured finding threshold is a **policy threshold failure**. Both block the
release, but they are reported separately.

“Absolute” means zero tolerance in every applicable scenario. “Measured” means
the approved qualification protocol and minimum sample sizes apply.

### 9.1 Product correctness

| Gate | Type | Release condition |
| --- | --- | --- |
| `GATE-PC-INV` | Absolute | Zero violations of three-axis, evidence-lineage, state, multi-label, resolved-override, and grouping invariants. |
| `GATE-PC-GOLDEN` | Absolute | All G-001–G-020 exact expectations and prohibited outcomes pass under their scripted profiles; no golden is silently relabeled. |
| `GATE-PC-DETERMINISTIC` | Measured plus absolute critical condition | AC-2: at least 95% deterministic precision and recall on sufficient holdout data; zero critical FN. |
| `GATE-PC-FINDING` | Absolute | AC-3 fields and evidence/next action exist for 100% of findings; deterministic locations/rules are exact and secret-safe. |
| `GATE-PC-RENDER` | Absolute | AC-4 semantic parity and stable IDs across terminal, Markdown, JSON, and CI; lossless grouping and visible coverage. |
| `GATE-PC-SEMANTIC` | Measured | AC-5 thresholds on sufficient independent data, with per-class and stability reporting. |
| `GATE-PC-AMBIGUITY` | Absolute plus measured actionability | Zero forced `pass`/`finding` on deliberate ambiguity; AC-6 actionability at least 80%; exact state/reason for abstention, candidate, not-run, and error. |

### 9.2 Privacy and security contracts

| Gate | Type | Release condition |
| --- | --- | --- |
| `GATE-PRIV-OFFLINE` | Absolute | All P0 deterministic families complete with network denied; zero network attempts. |
| `GATE-PRIV-DISCLOSURE` | Absolute | Zero provider starts without enabled semantic mode and manifest-specific consent; no provider/content/purpose scope expansion. |
| `GATE-PRIV-LEAKAGE` | Absolute | Zero fake-secret or unapproved script-body occurrences in model requests, outputs, logs, fingerprints, ordinary records, or external artifacts. |
| `GATE-PRIV-TRUST` | Absolute | Zero script executions, provider-direct decisions/authority, or scope/permission changes caused by analyzed content. |

### 9.3 Repair safety

| Gate | Type | Release condition |
| --- | --- | --- |
| `GATE-RS-AUTH` | Absolute | AC-8/AC-10: zero writes for absent, mismatched, expired, revoked, replayed, or non-substitutable authority; recheck before every operation. |
| `GATE-RS-PREVIEW` | Absolute | AC-9: every write has an exact preview whose digest matches the executed canonical operation list, including pre-authorized writes. |
| `GATE-RS-PRECONDITION` | Absolute | Zero writes after target/revision/identity/path/capability or prior-state-capture mismatch; unsupported/non-reversible work remains manual-only. |
| `GATE-RS-AT-MOST-ONCE` | Absolute | Confirmation, apply-attempt, and completed rollback replay cause zero repeated mutations. |
| `GATE-RS-VERIFY-RECORD` | Absolute | Exact post-image and proposal-condition verification are separate; every aggregate/target state and authority/proposal reference is unambiguous and attributable. |
| `GATE-RS-ROLLBACK` | Absolute | AC-11–AC-13: exact prior restoration when post-image is unchanged; zero overwrite/merge on conflict; partial-race and verification failures are explicit. |

Every claimed repair operation must pass the full gate matrix on every claimed
filesystem capability profile. Aggregate success cannot offset one safety
failure.

### 9.4 Compatibility and output contracts

| Gate | Type | Release condition |
| --- | --- | --- |
| `GATE-COMP-PROFILE` | Absolute | No version-dependent deterministic conclusion uses an unknown, stale, incompatible, uncited, or unreviewed rule; safe unsupported behavior is explicit. |
| `GATE-COMP-VERSION` | Absolute | Product, result schema, taxonomy, rule set, normalization, platform profile, semantic contract, grouping, and input revisions are independently attributable; relevant changes invalidate IDs/caches/qualification as specified. |
| `GATE-OUT-SCHEMA` | Absolute | Every sealed JSON/result/change artifact validates its published schema and closed enums; invalid graphs are execution failures, not partial policy success. |
| `GATE-OUT-BACKCOMP` | Absolute once a public contract exists | No silent removal/redefinition of required fields/enums or stable-ID meaning within a schema major version; breaking changes use a new major contract and compatibility/migration evidence. |

Stage 04 versions the test schema. The concrete product JSON schema and numeric
exit codes remain Stage 05 choices, but must satisfy these gates before being
published.

### 9.5 Reliability, resource behavior, and documentation

| Gate | Type | Release condition |
| --- | --- | --- |
| `GATE-REL-PARTIAL` | Absolute | Failures stay at the smallest honest unit; completed independent results survive; required gaps are never hidden or called pass. |
| `GATE-REL-REPEAT` | Absolute | Three deterministic repetitions are canonically equivalent; provider/renderer retries do not duplicate cases or mutations. |
| `GATE-REL-RESOURCE` | Absolute contract, Stage 05 threshold selection | Every retry, provider wait, parser/resource bound, and concurrent test has a declared limit/watchdog; no hang, leaked process, open handle, cache, or case state. No end-user latency SLO is invented by Stage 04. |
| `GATE-DOC-TRACE` | Absolute/manual | Canonical and Chinese docs, scenario schema, corpus, traceability, profile provenance, review status, deferred choices, and known gaps agree. |

The PRD gives no numeric latency or throughput target. Stage 04 therefore gates
bounded completion, isolation, and repeatability, not an unsupported performance
claim. Stage 05 may propose evidence-backed performance budgets separately.

## 10. Traceability and intentional gaps

[`traceability.csv`](../test-spec/traceability.csv) contains 155 source rows. It
maps:

- P0-R1 through P0-R31;
- P1-R1 through P1-R10;
- AC-1 through AC-17;
- every substantive taxonomy class, required state/qualifier/control class,
  and the core three-axis/evidence/adjudication/grouping contracts;
- G-001 through G-020;
- AD-01 through AD-14;
- all 21 Stage 03 component boundaries; and
- all 18 technology-neutral component contracts.

There are no intentional scenario-specification gaps for those required items.
The following execution gaps are intentional and visible:

1. No runtime-evidence producer or causal validation is tested as a shipped
   capability; only the reserved type and `runtime_validation_needed` boundary
   are tested.
2. Synthetic profiles exercise contracts, but a reviewed current Codex profile
   must be materialized before version-dependent rules can ship.
3. No real provider/model is qualified and no provider is required for
   deterministic release.
4. No repair operation is declared supported until Stage 05 chooses an
   allowlisted reversible operation and passes the complete matrix.
5. No product runner, physical result storage, CLI spelling, numeric exit code,
   CI platform, or performance SLO is selected here.
6. P2 non-Codex adapters, runtime traces, team governance, hosted interfaces,
   and unattended repair remain outside the MVP.

## 11. Test data governance

### 11.1 Provenance and permitted data

- Fixtures are synthetic and record their source document, author/reviewer
  role, creation date, schema version, fixture version, profile, and rationale.
- Fake secrets use unique sentinels such as
  `SYNTHETIC_SECRET_DO_NOT_SEND`; they are not copied from a real credential and
  must be absent from every prohibited sink.
- Production repositories, customer contracts, personal paths/content,
  telemetry, real credentials, and unredacted provider traffic are prohibited.
- Sanitized provider recordings may be used only for adapter contract tests
  after review confirms they contain no production/personal data or secrets.

### 11.2 Review, versioning, retirement, and localization

- Status is `draft`, `reviewed`, `disputed`, or `retired`. Disputed fixtures do
  not contribute to qualification metrics.
- G-001–G-020 IDs and normative expectations are stable. Changing decisive
  evidence, expected axes, acceptable uncertainty, or prohibited outcomes
  requires an approved amendment to the governing canonical documents, a new
  fixture version, and independent review. Tests cannot weaken a golden to make
  implementation pass.
- Additive execution metadata that does not affect adjudication still receives
  materialization review and a recorded change reason.
- Retirement preserves the old fixture and rationale; IDs are never reassigned.
  Replacement fixtures link to the retired case.
- English fixture semantics are canonical. Localized titles/rationales are
  projections. Chinese review documents and translated fixture descriptions
  are not active duplicate sources unless a localization test explicitly puts
  them in scope.

### 11.3 Change control and leakage prevention

Golden and qualification changes require diff review covering decisive
evidence, modality/exclusions, region, profile, expected axes, prohibited
outcomes, and traceability. Qualification suites are access-separated from
development and prompt/rule tuning. A post-run change cannot retroactively fix
a score; it creates a new suite version and run.

## 12. Environment, isolation, and execution profiles

1. Each case runs in a fresh temporary or virtual root with an explicit
   before-manifest and after-cleanup manifest. The developer repository and
   user configuration are never a target.
2. Deterministic suites deny network and provide no credentials. Provider
   simulations are local and scripted.
3. Live-provider qualification is a separate opt-in environment using only
   approved synthetic content and exact disclosure consent. Recordings are
   adapter fixtures, not accuracy ground truth.
4. Environment profiles declare case sensitivity, Unicode/path behavior,
   symlink support, identity observations, permissions, race-safe replacement,
   durable prior-state capability, and any unsupported repair operation.
5. Clock, session, expiry, revocation, and provider timing are injected and
   recorded. No test depends on ambient wall clock.
6. Concurrent changes occur at named barriers such as after all-target
   preflight or before the second apply/rollback operation. Timing races alone
   are not an acceptable oracle.
7. Input enumeration and canonical output ordering are deterministic. Random
   property runs record seed, generated value, and minimized counterexample.
8. Cleanup verifies files, metadata, symlinks, permissions, provider queues,
   caches, recovery material, open handles, processes, and network state. A
   cleanup failure is an execution failure and invalidates scoring.

## 13. Failure triage and artifacts

Every failing or invalid run produces a secret-safe reproduction bundle with:

- scenario ID/version, suite version, seed/repetition, exact failed assertion,
  lifecycle point, expected and actual typed states, and prohibited outcome;
- product, result-schema, taxonomy, rule-set, normalization, platform-profile,
  grouping, semantic-contract, adapter, provider/model, and CI-policy versions;
- frozen scope/consent/grant/proposal digests and a redacted input revision
  manifest with canonical relative identities and filesystem capabilities;
- inventory, check coverage, evidence IDs/kinds/lineage, case/group IDs, run
  outcome, renderer/CI outcomes, and partial diagnostics;
- model-call status, provider/model identity, request/input digest, safe request
  ID, response validation, retry count, and consent manifest—never credentials
  or unapproved raw content;
- proposal, authorization decision, per-target pre/post fingerprints, protected
  prior-state reference, verification, change record, rollback record, and
  barrier/fault timeline when mutation is involved;
- cleanup verification and environment/tooling diagnostics.

Artifacts use workspace-relative minimized locations and explicit
`redacted`/`withheld` markers. Secret-echo responses are quarantined; ordinary
failure reports contain only a safe event and digest.

Triage assigns one primary class before changing code or fixtures:

| Class | Meaning |
| --- | --- |
| Product defect | Implementation violates a valid canonical oracle. |
| Fixture defect | Materialization does not express its approved decisive evidence or event. |
| Oracle defect | Expected result conflicts with or is ambiguous under canonical documents. |
| Profile defect | Rule provenance, compatibility, case/path semantics, or limit is wrong/stale. |
| Environment/capability defect | Declared filesystem, clock, network, permission, or provider capability was not actually supplied. |
| Runner/evaluator defect | Isolation, fault injection, parsing, scoring, redaction, or cleanup infrastructure is wrong. |
| Provider qualification instability | Live provider behavior varies while local contracts remain correct; it is not reclassified as deterministic proof. |

Unresolved classification blocks the affected qualification cell. A fixture or
oracle correction follows change control and does not erase the original run.

## 14. Stage 04 decisions and rejected alternatives

| ID | Decision made now | Rejected alternative and rationale |
| --- | --- | --- |
| TD-01 | Use a versioned, technology-neutral JSON scenario-suite contract with every boundary and oracle explicit. | Prose-only cases omit machine-checkable negative assertions and drift across implementations. |
| TD-02 | Make interaction question/region/dimension the diagnostic scoring unit. | File- or alert-line scoring rewards duplicates and cannot represent G-018. |
| TD-03 | Use test-only `not_applicable` for non-diagnostic contract scenarios. | Inventing product `pass`/`not_run` states for repair or renderer tests would corrupt the three axes. |
| TD-04 | Materialize files as synthetic virtual entries plus precise generators and named faults. | Depending on developer/global configuration is unsafe and irreproducible; creating a runner now would begin Stage 05. |
| TD-05 | Preserve G-001–G-020 exactly as normative regression cases but do not treat them as statistically sufficient. | Relabeling goldens or claiming twenty cases meet AC-2/AC-5 would weaken approved behavior. |
| TD-06 | Separate development, normative regression, and qualification holdout corpora. | One visible corpus invites evaluation leakage and optimistic tuning. |
| TD-07 | Give no TP credit to candidate/abstention on an expected finding; report exact-state and coverage separately. | Partial credit can game recall while hiding indecision. |
| TD-08 | Separate absolute safety/privacy/invariant gates from measured product targets. | Averaging a secret leak or unauthorized write into an accuracy score is unacceptable. |
| TD-09 | Compare renderer semantics to one sealed graph, not independent textual snapshots. | Independent snapshots can agree superficially while states, IDs, or coverage diverge. |
| TD-10 | Canonical repeatability excludes only declared volatile fields. | Byte-for-byte whole-artifact comparison would fail on legitimate timestamps; broad normalization would hide real drift. |
| TD-11 | Require minimum sample strata and report Wilson intervals without claiming current attainment. | A percentage from a tiny or class-skewed set is not release evidence. |
| TD-12 | Separate scripted/recorded adapter tests from live-provider qualification and invalidate qualification on provider/model change. | Recorded success cannot prove live semantic quality; a mandatory live provider would violate offline deterministic operation. |
| TD-13 | Parameterize the full repair matrix over every later supported operation and capability profile. | A single happy-path file edit cannot establish authorization, concurrency, verification, or rollback safety. |
| TD-14 | Keep machine-readable traceability for requirements, taxonomy, goldens, decisions, components, and contracts. | Narrative-only traceability makes omissions hard to detect. |
| TD-15 | Gate bounded completion and cleanup but defer numeric latency/throughput SLOs. | The PRD provides no evidence-backed performance target to adopt. |

## 15. Internal Stage 04 review

The 2026-08-17 documentation review performed the following checks before
handoff:

- **Consistency:** all scenarios keep check state, substantive label, and
  validation qualifier separate; non-diagnostic tests use only the test-level
  sentinel.
- **Traceability:** every required P0/P1 item, AC-1–AC-17, Stage 02 class and
  core adjudication contract, G-001–G-020, AD-01–AD-14, architecture component,
  and technology-neutral contract has at least one scenario and gate mapping.
- **Golden preservation:** each materialized golden retains decisive evidence,
  exact expected axes, uncertainty, and prohibited misclassification; static
  evidence is never reinterpreted as runtime selection or causality.
- **Privacy/trust:** all data is synthetic; scopes and consents are separate;
  secret/script, provider, output, recovery, and untrusted-content paths have
  negative assertions.
- **Failure modes:** positive, negative, boundary, abstention, not-run, error,
  partial result, renderer, CI, authorization, apply, verification, rollback,
  concurrency, and cleanup failures are distinguished.
- **Repair safety:** exact preview/digest, scope/session/time/revocation,
  all-target preflight, prior/post capture, at-most-once, stop-on-failure,
  verification, safe rollback, and race-after-preflight behavior are covered.
- **Scope:** no product implementation, runner, framework/provider/CI choice,
  real platform claim, packaging, or release claim was introduced.

### 15.1 Handoff condition

Stage 04 is reviewable, not release evidence. Stage 05 may begin only after
reviewers accept this contract or record amendments. Any Stage 05 implementation
must report which scenarios are executable, which remain blocked by an
unselected profile/operation/provider, and must not claim PRD targets until the
independent measurement protocol has actually run.
