# Agent Doctor Detailed Design and Architecture

| Field | Value |
| --- | --- |
| Status | Review draft |
| Architecture version | 0.1 |
| Date | 2026-08-17 |
| Canonical language | English |
| Companion review copy | [中文](detailed-design-and-architecture.zh-CN.md) |
| Governing product definition | [Product requirements](product-requirements.md) |
| Governing diagnostic contract | [Conflict taxonomy and golden examples](conflict-taxonomy-and-golden-examples.md) |
| Project stage | Stage 03 — detailed design and architecture only |

## 1. Purpose, status, and boundaries

This document turns the approved Stage 01 product behavior and Stage 02
diagnostic meanings into an implementable, testable architecture for the
Codex-first local CLI MVP. It defines domain contracts, component boundaries,
data and control flows, failure semantics, repair safety, result representation,
and traceability. It does not contain product implementation code.

The PRD and taxonomy remain authoritative. In particular:

- analysis is read-only by default;
- deterministic diagnosis is local and offline;
- semantic diagnosis runs by default for an explicit comprehensive diagnosis,
  remains disableable/narrowable, and is exactly disclosed and digest-bound;
- static evidence does not prove runtime selection or causality;
- precision and explainability take priority over coverage;
- `pass`, `finding`, `candidate`, `insufficient_evidence`, `not_run`, and
  `error` are check states, not conflict classes;
- substantive labels and `runtime_validation_needed` remain independent axes;
- every supported write is exactly previewed, boundedly authorized, verified,
  recorded, and safely reversible.

Stage 04 will materialize fixtures, scenarios, measurement protocols, and
quality gates. Stage 05 will select implementation technologies and write code.
This document must not be read as completing either later stage.

## 2. Architecture goals, constraints, and trust boundaries

### 2.1 Goals

1. Produce one evidence-backed diagnostic result that terminal, Markdown, JSON,
   and CI consumers can project without re-adjudicating it.
2. Make every deterministic conclusion reproducible from observed facts and a
   versioned rule or platform profile.
3. Preserve uncertainty and partial coverage without converting either into a
   pass.
4. Minimize filesystem and model disclosure scope and make every expansion
   visible before it occurs.
5. Separate diagnosis, repair planning, authorization, application,
   verification, and rollback so no earlier capability implies a later one.
6. Detect concurrent changes before apply and rollback and refuse unsafe
   overwrites.
7. Keep platform-dependent Codex behavior attributable and replaceable as the
   platform evolves.
8. Provide stable identifiers and sufficient version metadata for review,
   baselines, and later evaluation.

### 2.2 Constraints

- The MVP is a local, Codex-first CLI, not a hosted service or general agent
  platform.
- Supported inputs are the PRD sources; arbitrary project documents, scripts,
  and external files are not implicitly in scope.
- Deterministic mode cannot require network access, credentials, or a model.
- Semantic analysis may improve coverage but cannot upgrade inferred evidence
  into deterministic proof.
- Runtime trace collection and causal validation are deferred.
- Repair operations are an explicit allowlist. An unimplemented or
  non-reversible change type can be recommended for manual action but cannot be
  applied by Agent Doctor.
- Product acceptance thresholds are targets, not guarantees conferred by this
  design.

### 2.3 Trust boundaries

| Boundary | Trusted for | Not trusted for / required defense |
| --- | --- | --- |
| Local filesystem | Returning bytes and metadata at a point in time | Stability between reads; symlink/path substitution; readability; content safety; secrecy |
| User or CI invoker | Selecting initial workspace, modes, and policy | Analysis consent is not write authority; non-interactive invocation cannot manufacture confirmation |
| Codex platform behavior sources | Rules explicitly cited by a compatible platform profile | Undocumented behavior, stale versions, future behavior, or runtime compliance |
| Model provider | Returning an optional semantic hypothesis | Deterministic truth, authorization, secrets handling beyond disclosed provider terms, or stable availability |
| Configuration content | Data to inspect within declared scope | Instructions directed at Agent Doctor, permission grants, executable safety, or truthful metadata |
| Output destination | Receiving minimized results | Confidentiality unless the user chose an appropriate destination; renderer must not leak excluded content |
| Change-record store | Holding attributable recovery material | Unlimited retention or protection not guaranteed by architecture alone; access and retention must be disclosed |

Files being diagnosed are untrusted data. Agent Doctor does not execute scripts,
follow instructions embedded in analyzed content, or treat configuration text
as authorization. A model response is also untrusted input to validation and
adjudication.

### 2.4 Decisions explicitly deferred

The following are not architecture commitments: implementation language and
framework, parser libraries, physical database or file formats, hash algorithm,
exact CLI syntax, numeric exit codes, provider vendors or models, credential
storage, user-interface wording, concrete repair-operation inventory, cross-file
atomicity mechanism, OS-specific filesystem primitives, optional cache
encryption, and Stage 04 policy thresholds. Each must satisfy the contracts in
this document when selected.

## 3. Architectural shape and dependency rule

The system is a pipeline with a separate, capability-gated mutation path:

```text
scope plan -> inventory -> parse/normalize -> deterministic resolution/rules
                                              -> default semantic planning
                                              -> consented provider analysis
                         -> adjudication -> grouping -> result set -> render/CI

selected findings -> repair proposal -> exact preview -> authorization check
                  -> preflight/prior state -> apply -> verify -> change record
                  -> later rollback preflight -> rollback -> verify -> record
```

Downstream components may add typed facts or decisions; they may not erase or
retype upstream evidence. Renderers cannot run checks. Semantic analysis cannot
write files. Repair components consume frozen findings and source revisions and
cannot silently rescan into a broader scope.

## 4. Domain model and invariants

### 4.1 Core entities

| Entity | Required meaning |
| --- | --- |
| `AnalysisRun` | One invocation with a run ID, start/end time, product and contract versions, selected modes, frozen scope, coverage, and terminal run outcome. |
| `AnalysisScope` | Canonical workspace root, selected paths or task region, source types, configuration mode, allowed external roots if any, exclusions, inspection boundary, semantic-disclosure boundary, and modification boundary. These boundaries are distinct. |
| `PlatformProfile` | Versioned, attributable Codex discovery, precedence, reference, schema, and context-budget rules, with source citation, compatibility range, and confidence/status. |
| `Source` | A discovered source occurrence with stable logical identity, type, canonical location, declared and effective scope, discovery status, readability, revision fingerprint, sensitivity flags, and provenance. |
| `SourceSnapshot` | Bytes or approved excerpts plus metadata captured at a stated observation time. Content may be withheld while metadata remains observed evidence. |
| `Claim` | The smallest normalized obligation, prohibition, permission, trigger, scope statement, output constraint, reference, or configuration assertion, linked to exact source wording and qualifiers. |
| `ApplicabilityRegion` | A composable expression over paths, request/task witnesses, modes, conditions, inclusions, and exclusions. It records whether intersection is proven, inferred, empty, or unknown. |
| `Dimension` | The interaction subject, such as required action, forbidden action, question policy, output form, trigger, reference validity, configuration, precedence, or context use. |
| `EvidenceRecord` | An immutable observed, derived, inferred, or runtime item with producer, timestamp, source references, rule/provider attribution, sensitivity treatment, and lineage. |
| `CheckDefinition` | A stable check/rule ID and version, reviewable question template, supported modes/source types, required prerequisites, decision contract, and possible coverage/failure outcomes. |
| `CheckExecution` | One defined diagnostic question and check family with lifecycle, final check state, reason, coverage, input revisions, and evidence references. |
| `InteractionCase` | The atomic adjudication unit: frozen question, sources/claims, shared region, dimension, evidence, three output axes, impact, confidence, counterexample, and next action. |
| `SubstantiveAssessment` | A label applied to explicit claim IDs, region ID, and dimension ID. Multiple assessments may exist only where the taxonomy multi-label rules permit. |
| `ValidationQualifier` | A qualifier on a specific hypothesis; MVP currently supports `runtime_validation_needed`. |
| `FindingGroup` | One user-visible problem or explanatory relationship that groups substantially identical cases while retaining all case and evidence locations. |
| `NextAction` | A bounded manual step, evidence request, runtime validation proposition, repair proposal request, or no-action explanation. It never carries authority itself. |
| `ResultSet` | The immutable canonical graph for a completed run, including inventory, coverage, checks, cases, groups, diagnostics, versions, and reproducibility metadata. |
| `RepairProposal` | An exact, immutable change plan derived from selected result IDs and source revisions, including targets, operations/diffs, rationale, effects, risks, verification, rollback support, preconditions, and digest. |
| `AuthorizationGrant` | A separately issued capability bounded by grant ID, subject/session, canonical target constraints, operation classes, validity interval/session, revocation state, and optional proposal digest. |
| `ChangeRecord` | Attributable lifecycle record for an apply or rollback attempt, with proposal and grant references, actor/session, per-target pre/post fingerprints, protected prior state, verification, and unambiguous aggregate/per-target states. |

### 4.2 Evidence and provenance

Evidence kinds are closed and non-interchangeable:

- `observed`: directly read text, path, metadata, existence, readability,
  configuration, consent, mode, or filesystem state;
- `derived`: reproducible output of observed evidence plus named, versioned
  rules; every item contains parent evidence IDs and a derivation rule ID;
- `inferred`: semantic interpretation, including all model output unless a
  separate deterministic derivation independently establishes the same fact;
- `runtime`: evidence from an actual execution with recorded conditions. The
  model supports the type, but MVP producers do not collect it.

An evidence record is append-only. A renderer may redact its presentation but
cannot change its kind. Agreement between multiple models remains inferred
evidence. A later runtime or deterministic record may corroborate an inference,
but does not retroactively change the inference's provenance.

### 4.3 State, label, qualifier, severity, and confidence invariants

The MVP substantive-label registry contains `semantic_conflict`,
`scope_overlap`, `behavioral_redundancy`, `complementarity`,
`precedence_override`, `invalid_reference`, `stale_reference`,
`context_budget_risk`, and `configuration_risk`. `no_material_relation` is a
golden/control label under the restricted rule below; it is not a problem
finding. Registry entries carry the taxonomy version and cannot be added,
removed, or redefined by a detector or provider.

1. Every defined check has exactly one final state: `pass`, `finding`,
   `candidate`, `insufficient_evidence`, `not_run`, or `error`.
2. A state is never stored in the substantive-label field.
3. `not_run` names the skipped check and reason; it has no substantive severity
   or confidence.
4. `error` names the attempted operation and failure; it does not invent a
   configuration defect or severity.
5. `insufficient_evidence` names missing decisive evidence and the smallest
   resolving step; confidence, if present, is confidence in abstention.
6. `finding` requires sufficient decisive evidence under its rule.
7. Low-confidence substantive problems normally remain `candidate`.
8. `runtime_validation_needed` attaches to an exact, falsifiable proposition,
   normally on a candidate, and never upgrades its state.
9. Severity measures likely impact and is independent of confidence. Potential
   severity is distinct from assigned severity for an established issue.
10. `semantic_conflict`, `behavioral_redundancy`, and `complementarity` cannot
    apply to the same claims, region, and dimension. They may coexist in a
    group only with explicit different dimensions or subregions.
11. A resolved override cannot remain an active semantic conflict.
12. `no_material_relation` is available to golden/control results and
    explanatory pass records, not emitted as a problem finding.

### 4.4 Scope and source invariants

1. The scope shown before scanning is frozen and digestible; later changes
   create a new scope revision requiring presentation again.
2. Discovery scope, local inspection scope, semantic-disclosure scope,
   modification scope, and rollback targets are independently represented.
3. Inclusion in one scope never implies inclusion in another.
4. Every discovered, ignored, shadowed, truncated, missing, unreadable, or
   deliberately excluded supported source gets an inventory record.
5. Canonicalization cannot authorize a path outside the declared boundary.
6. A reference is resolved relative to its declaring source under a named
   resolver rule, not the process working directory.
7. Exiting an allowed root is decidable from normalized metadata and does not
   justify reading the outside target.
8. Applicability and effectiveness are separate: a discovered source may be
   ineligible, inapplicable, shadowed, or effective.
9. Unknown platform behavior cannot be replaced with an intuitive precedence
   or context rule; the affected question abstains or becomes a conditional
   candidate.

### 4.5 Identity, grouping, and version invariants

- Run IDs and evidence occurrence IDs are unique per run. Rule IDs, check IDs,
  source logical IDs, case fingerprints, and group fingerprints are stable when
  their defining normalized inputs and contract versions are unchanged.
- A case fingerprint is derived from the rule/question, logical sources and
  claims, region, dimension, and relevant normalization/taxonomy versions. It
  excludes timestamps, absolute user-specific prefixes where a workspace-
  relative identity suffices, secrets, and rendered prose.
- A changed decisive claim or scope creates a new fingerprint; it is not hidden
  behind the old baseline identity.
- Grouping has an explicit version and reason. It never discards member cases,
  evidence, dimensions, or locations.
- Product, result-schema, taxonomy, rule-set, normalization, platform-profile,
  and semantic-contract versions are independent metadata fields.

## 5. Component boundaries and responsibilities

| Component | Responsibilities | Must not do |
| --- | --- | --- |
| CLI/session coordinator | Parse invocation intent, establish run/session identity, sequence capabilities, surface preview/consent, and choose output sinks. | Infer write permission, adjudicate findings, or hide incomplete coverage. |
| Scope presenter and policy guard | Build and display proposed scan/inspection/disclosure/modification scopes; freeze accepted scope; enforce boundary checks. | Expand scope due to a discovered reference without a new disclosed decision. |
| Platform profile registry | Supply versioned schemas and documented discovery, precedence, resolver, and budget rules with provenance. | Guess undocumented behavior or silently use a different platform version. |
| Discovery and inventory | Enumerate supported candidates, source chains, status, and metadata under the frozen discovery scope. | Parse semantics, follow forbidden references, or omit inaccessible sources. |
| Safe reader/content broker | Mediate metadata reads, content reads, excerpts, redaction, sensitivity classification, and model-eligible bundles. | Execute content, expose unapproved scripts/secrets, or equate inspect permission with model consent. |
| Parser and normalizer | Produce source snapshots, structured declarations, claims, qualifiers, and parse diagnostics with exact locations. | Resolve semantic conflicts, discard source text, or normalize away modality/exclusions. |
| Reference and configuration resolver | Resolve supported declarations, schemas, existence/readability/type, scope escapes, and compatibility facts. | Read outside scope to confirm an escape or classify semantic staleness from age alone. |
| Precedence and applicability resolver | Build source chains, applicability regions, effective/latent claims, and shared-region facts from platform rules. | Invent a winner or claim runtime compliance. |
| Deterministic rule engine | Execute reproducible duplicate, validity, metadata, precedence, and budget checks against typed facts. | Call a model, use unversioned limits, or label a failed check as pass. |
| Semantic coordinator | Select minimal eligible claims, disclose/provider-gate submission, call an adapter, validate response shape/citations, and record inferred evidence. | Send secrets/scripts by default, grant authority, or publish provider labels directly as findings. |
| Provider adapter | Translate the neutral semantic request/response contract for one provider and expose provider/model/policy metadata. | Access arbitrary files or decide Agent Doctor state/severity. |
| Adjudicator | Apply ordered taxonomy procedure, counterexample check, multi-label rules, confidence/severity rules, and abstention. | Erase upstream errors or turn inference into observed/derived proof. |
| Deduplicator and grouper | Compute stable case/group identities and consolidate one user problem across evidence locations. | Merge different questions, regions, or dimensions merely because files match. |
| Result assembler | Validate invariants and seal the canonical result set with coverage and reproducibility metadata. | Re-run analysis during rendering. |
| Terminal/Markdown/JSON renderers | Project the same result graph with channel-appropriate detail and secret-safe excerpts. Rank review items without changing them; terminal shows the highest-severity items, representative lower-severity items, cited source text/model rationale/counterexample provenance, and explicit omitted counts, while Markdown/JSON retain complete detail. | Change state, labels, severity, or coverage; present an unasked or unanswered semantic question as a risk. |
| CI policy evaluator | Evaluate a separately configured threshold against the sealed result and produce `satisfied`, `policy_failed`, or `execution_failed`. | Delete below-threshold findings from durable output or confuse policy failure with tool failure. |
| Repair planner | Convert selected findings into an allowlisted, reversible exact proposal and verification plan. | Write, broaden targets, or propose an unsupported write as auto-applicable. |
| Authorization service | Issue/import, validate, revoke, and expire bounded grants; bind exact confirmations to proposal digests. | Treat analysis/model consent as a grant or relax a target/operation boundary. |
| Apply coordinator | Revalidate preview, grant, paths, revisions, and preconditions; capture prior state; execute approved operations; stop on conflict; record outcomes. | Re-plan during apply, continue after authority loss, or overwrite a concurrent change. |
| Post-change verifier | Check exact post-images and proposal-specific semantic/deterministic conditions without widening scope. | Declare success only because writes returned successfully. |
| Change ledger and rollback coordinator | Preserve attributable records and protected prior states; preflight current post-images; restore only when safe; verify and record rollback. | Roll back through a mismatch or claim recoverability without captured state. |

## 6. Technology-neutral component contracts

Every contract returns a value plus typed diagnostics; it does not communicate
ordinary partial failure solely through process termination. Inputs include
scope and version references rather than relying on ambient working-directory
state.

| Contract | Input -> output | Failure and idempotency semantics |
| --- | --- | --- |
| `PlanScope` | user selection + platform selection + modes -> presented `AnalysisScope` | Invalid or ambiguous roots prevent scan start. Repeating identical inputs yields the same normalized scope digest, excluding observation time. |
| `Inventory` | frozen scope + platform profile -> source records + coverage events | Per-source access failures are retained; catastrophic inability to inspect the root marks affected checks `error`. Read-only and repeatable for the same filesystem snapshot. |
| `ReadSource` | source ID + allowed read purpose -> snapshot/excerpt or typed denial/failure | Scope denial is not retried as broader access. Read is side-effect-free; revision fingerprint accompanies content. |
| `ParseAndNormalize` | snapshot + source schema/normalization version -> claims + diagnostics | Malformed content may yield usable partial claims plus explicit parse errors and completeness flags. Same bytes/version produce equivalent normalized facts. |
| `ResolveReference` | declaration + source location + scope + resolver profile -> normalized target/status/evidence | Never reads an out-of-bound target. Unsupported syntax produces the configured unsupported/insufficient result, not a guessed path. |
| `ResolveApplicability` | claims + source chain + scope + precedence profile -> regions/effectiveness/lineage | Missing decisive rules produce unknown effectiveness and an abstention dependency. Deterministic for identical inputs/profile. |
| `RunDeterministicCheck` | check definition + typed facts -> check execution + cases | A started internal failure is `error`; absent decisive in-scope fact is `insufficient_evidence`; disabled/out-of-scope is `not_run`. No network side effects. |
| `BuildSemanticDisclosure` | candidate questions + eligible excerpts + policy -> exact disclosure manifest | Any excluded required content remains excluded and drives abstention. Digest binds provider and eligible content handles. |
| `RunSemanticCheck` | approved manifest + provider config -> response envelope + inferred evidence | Unavailable before attempt is `not_run`; transport/schema failure after start is `error`; completed ambiguity is adjudicated as candidate/abstention. Provider retries must use a request idempotency key when supported and never duplicate findings. |
| `Adjudicate` | question + typed evidence + taxonomy version -> interaction case | Invariant violation is an architecture diagnostic, not a forced label. Same evidence and contract versions produce semantically equivalent adjudication. |
| `GroupCases` | cases + grouping version -> finding groups + member mapping | Stable and lossless; rerun does not duplicate members. |
| `Render` | sealed result + renderer policy -> terminal/Markdown/JSON artifact | Presentation failure does not mutate the result. A renderer indicates redactions and cannot suppress coverage gaps. |
| `EvaluateCI` | sealed result + explicit policy -> CI outcome + policy decisions | Evaluation is pure/idempotent. Policy failure and execution failure stay distinct. Numeric shell mapping is deferred but must be documented when selected. |
| `ProposeRepair` | selected stable IDs + current revisions + operation allowlist -> proposal or unsupported/manual action | Pure planning; identical inputs and canonical operation representation yield the same proposal digest. No write occurs. |
| `ValidateAuthorization` | proposal + grant + session/time/revocation state -> authorization decision | Rechecked immediately before apply and before each operation. Denial has zero writes. Confirmation tokens are single-proposal and single-use. |
| `ApplyProposal` | exact proposal + valid decision -> change record | At-most-once for a proposal/apply-attempt key. A replay reports prior outcome rather than repeating writes. Stops at first conflict/failure; reports every target as applied, unchanged, not attempted, conflicted, or failed. |
| `VerifyChange` | proposal + observed post-state -> verification result | Repeatable, read-only, and target-bounded. Distinguishes exact post-image, diagnostic-condition verification, and verification error. |
| `RollbackChange` | change record + current state + valid rollback authority -> rollback record | All targets are preflighted before restoration. Any post-image mismatch refuses rollback before writes; replays return the recorded result. |

## 7. End-to-end data and control flows

### 7.1 Offline deterministic diagnosis

1. The coordinator constructs the proposed analysis scope, enumerating roots,
   source types, exclusions, inspection limits, semantic mode and selection
   policy, and read-only authority, and displays it before scanning.
2. The scope guard freezes the accepted scope and selected platform profile.
3. Inventory enumerates every supported candidate and records discovered,
   ignored, shadowed, truncated, missing, unreadable, and excluded states.
4. The content broker reads only permitted local metadata/content and creates
   revisioned observations. No network call is available on this path.
5. Parsers preserve original wording and qualifiers while creating normalized
   declarations and claims.
6. Reference/configuration and precedence/applicability resolvers run before
   semantic comparisons. All derivations cite profile and parent evidence.
7. Deterministic rules execute independently where possible. One source failure
   does not discard unrelated completed results.
8. Adjudication applies the taxonomy order, shared-region proof, dimension
   isolation, counterexample check, and abstention rules.
9. Equivalent cases are grouped losslessly. The assembler seals one result set,
   including coverage gaps and version metadata.
10. Renderers and CI consume that result set. A deterministic scan with no
    provider panel reports enabled semantic work as pending execution; disabled
    or unavailable semantic check families are explicitly `not_run`, never pass.

### 7.2 Default semantic planning and manifest-bound model diagnosis

1. Deterministic discovery and resolution complete first.
2. The semantic coordinator plans unresolved, in-scope questions by default.
   Exact inclusion/exclusion selectors can narrow the bounded auto scope.
3. The content broker excludes credentials, detected secrets, executable
   scripts, unapproved bodies, unrelated referenced files, and non-decisive
   context. It creates content handles and minimized excerpts.
4. Before a standalone invocation, the user receives a disclosure manifest
   naming the provider, model/configuration identity where knowable, source
   locations, excerpt/content categories, exclusions, purpose, and provider-side
   retention/caching facts known to the adapter. An explicit one-shot semantic
   diagnosis instead authorizes only its immediately generated manifest and
   records the same fields in local artifacts before provider start. Both paths
   bind execution to the exact digest and remain separate from write authority.
5. Two blind analysts run concurrently in isolated ephemeral contexts. They
   receive the same frozen questions and evidence in canonical and reversed
   source order, cannot see one another, and return one cited answer per question.
6. After both answers validate, a third fresh-context judge receives the two
   responses and disclosed handles. It records consensus, a resolved
   disagreement, a challenge, or insufficient evidence without setting product
   state, severity, confidence, provenance, or repair authority.
7. Each provider request contains the frozen question,
   relevant claims and qualifiers, region/dimension context, permitted excerpts,
   taxonomy meanings needed for the task, and instruction to abstain. It does
   not receive arbitrary repository context or raw credentials.
8. The adapter validates structure, role/question joins, and citations to
   supplied handles. Returned
   hypotheses are recorded as inferred evidence with provider, model, adapter,
   prompt-contract, request, and input-digest provenance.
9. The local adjudicator—not the provider—assigns check state, labels,
   qualifiers, severity, and confidence. Only corroborated analyst consensus can
   become decisive; a judge-resolved disagreement is at most a candidate.
10. The sealed result includes both deterministic results and precise semantic
   coverage/outcomes.

### 7.3 Degraded, not-run, insufficient, and error behavior

| Condition | Required behavior |
| --- | --- |
| Semantic mode disabled or provider unavailable before a check starts | Deterministic run completes; each affected semantic check is `not_run` with reason. |
| Provider request starts then times out, fails, or returns unusable structure | Affected check is `error`; completed deterministic/semantic checks remain. |
| Check completes but decisive authorized content or platform rule is missing | `insufficient_evidence`, missing fact, reason, and bounded next step. |
| Static evidence supports a falsifiable runtime proposition | `candidate` with the relevant label and `runtime_validation_needed`; no runtime outcome is asserted. |
| One source becomes unreadable during a validity check | That check is `error`; independent prior findings remain, and downstream questions may separately abstain because the source is unavailable. |
| Result assembly invariant fails | Run outcome is execution failure; preserve inspectable partial diagnostics, do not emit a deceptively complete canonical result. |
| One renderer fails | Canonical result and other renderers remain valid; failed output is reported as an output error. |
| CI threshold is exceeded with a valid result | `policy_failed`, not `execution_failed`; durable reports still contain all findings. |

Run completion is summarized independently from per-check state. `complete`
means a valid result was sealed, every enabled in-scope check reached a
non-error terminal state, and any `not_run` was already declared disabled or
out of scope in the frozen plan. `complete_with_gaps` means a valid result was
sealed but an expected capability was unavailable, a check errored, or a
prerequisite remained partial.
`execution_failed` means a trustworthy canonical result could not be sealed.
None of these summaries changes an individual check state. CI additionally
declares which check families/modes are execution-required: an unmet required
family yields CI `execution_failed`; a valid, sufficiently covered result that
exceeds a finding threshold yields `policy_failed`; optional gaps remain visible
but do not automatically become policy success or failure.

### 7.4 Repair proposal and bounded authorization

1. The user selects stable finding/case IDs. Selection alone grants no write
   authority.
2. The planner confirms that each proposed operation belongs to the supported,
   reversible allowlist and stays inside modification scope.
3. It creates an immutable proposal containing canonical targets; exact
   before/after representation or equivalent exact operation list; source
   revision preconditions; rationale; expected effect; risks; verification;
   prior-state needs; rollback availability; and proposal digest.
4. The exact proposal is rendered before every write, including when an
   existing pre-authorization could cover it.
5. Authorization is satisfied only by either:
   - a valid grant whose canonical target constraints, operation classes,
     session/subject, validity interval, and revocation state cover the exact
     proposal; or
   - explicit confirmation bound to this proposal digest, session, targets,
     and operations.
6. Grants and confirmations are not transferable from scan consent, inspection
   approval, or model disclosure. A changed proposal has a new digest and needs
   a new authorization decision.
7. Revocation or expiry is checked at apply start and before every operation.
   Loss of authority stops further writes and is recorded.

### 7.5 Apply and verification

1. Resolve canonical target identities again without following a newly unsafe
   path; verify they remain within modification scope and match proposal
   identities.
2. Preflight all targets against expected revision fingerprints, type,
   symlink/link identity, permissions needed for the approved operation, and
   operation-specific conditions. A mismatch causes zero writes.
3. Capture the exact relevant prior state and metadata required for restoration
   before the first write. If durable, protected recovery material cannot be
   captured, the operation is unsupported and apply stops.
4. Revalidate proposal digest, authorization, revocation, and expiry.
5. Immediately before each operation, repeat the target identity, path, and
   revision precondition check, then apply it in the approved order without
   replanning. Use a target-local compare-and-replace or equivalent primitive
   that closes the check/write race. If the active platform cannot provide an
   adequate primitive for that operation, the write type is unsupported there.
   Cross-target atomicity is not assumed.
6. After each operation, capture the observed post-image fingerprint and record
   state. On failure or authority loss, stop; do not continue into unapproved
   compensation. The record distinguishes `applied`, `partially_applied`,
   `rejected`, `conflicted`, and `failed` aggregates plus per-target detail.
7. Verify exact post-images and proposal-specific conditions. Write success and
   verification success are separate. Aggregate state can be
   `applied_unverified` or `verification_failed` when appropriate.
8. Seal an attributable change record with no raw credentials or unnecessary
   secrets and present the bounded rollback action.

### 7.6 Safe rollback and concurrent-change protection

1. Rollback refers to one sealed change record and only its successfully
   applied targets. It requires valid authority for the reverse operation; the
   original analysis/model consent is irrelevant.
2. Before any restoration, preflight every target by comparing current identity
   and content/metadata against the recorded post-image. Missing or changed
   targets are conflicts unless the recorded reverse operation explicitly
   defines that exact state.
3. If any target differs, refuse the entire rollback before writing. Report the
   conflicting target and preserve both current state and recovery material.
   Agent Doctor does not overwrite or automatically merge unrelated work.
4. If all targets match, repeat the identity and post-image comparison
   immediately before each reverse operation, then restore the captured prior
   state using a race-safe target-local primitive. A new mismatch stops without
   overwriting that target; if earlier targets were already restored, the record
   explicitly says `rollback_partially_applied`. Verify exact prior fingerprints
   and required metadata, and record `rolled_back`, `rollback_conflicted`,
   `rollback_partially_applied`, `rollback_failed`, or
   `rollback_verification_failed` with per-target states.
5. Repeating a completed rollback is a no-op report, not a second mutation.

## 8. Discovery, scope, and platform-rule boundaries

### 8.1 Scope sets

The architecture maintains explicit sets instead of one overloaded “scope”:

- `discovery_candidates`: locations the versioned adapter is allowed to
  enumerate;
- `inventoried_sources`: every observed candidate and its status;
- `inspection_eligible`: sources/content that local deterministic analysis may
  read;
- `applicable_sources`: sources whose declared/path conditions intersect the
  selected task region;
- `effective_claims`: claims remaining after deterministic precedence;
- `semantic_eligible`: the exact content permitted for a disclosed model call;
- `modifiable_targets`: canonical targets covered by both product support and
  a proposal/authorization;
- `rollback_targets`: applied targets whose recorded post-images still match.

Transitions are recorded with reason and rule ID. No later set may silently
expand an earlier boundary.

### 8.2 Platform profiles

A platform profile is data/contract, not hidden control flow. It names:

- ecosystem and platform version compatibility;
- discovery roots, filenames, chain/override behavior, defaults, and exclusions;
- manifest/configuration schemas and unknown-field policy;
- supported reference forms, base-location rules, variable expansion, path and
  case semantics;
- context/list limits, units, loading phase, ordering/truncation behavior, and
  evidence source;
- provenance URI/document/version, capture date, profile version, and review
  status.

An exact documented rule may support derived evidence. A profile marked
unknown, incompatible, or stale cannot support a deterministic winner, schema
failure, or budget finding. The result records the chosen profile and every
rule used. Updating a profile is a rule-set change and may change fingerprints;
it is never silent.

### 8.3 Reference resolution

Resolution is lexical and metadata-first: parse the supported declaration,
select the declaring source as base, expand only version-supported variables,
normalize without escaping an allowed root, determine target kind, and then
inspect only permitted metadata/content. Symlink and case behavior are supplied
by the platform/filesystem profile. Escapes are reported without opening the
outside file. Transient I/O exhaustion produces `error`; unsupported or
unknown resolution semantics produce the appropriate abstention/configuration
outcome rather than a guessed target.

### 8.4 Context-budget rules

A deterministic budget finding requires all of: a measured quantity in the
correct unit and loading phase, a compatible documented limit/ordering rule,
eligible inventory under that rule, and exceedance or observed truncation.
Bytes are not silently converted to tokens. Unknown allocation permits an
inventory measurement or candidate/abstention, not a deterministic finding or
pass. The profile and measurement lineage appear in evidence.

## 9. Semantic-analysis and provider boundary

### 9.1 Neutral request contract

A semantic request contains only:

- stable question/check ID and taxonomy version;
- minimized claim excerpts with source handles and location ranges;
- preserved modality, exceptions, scope/region, dimension, and witness;
- deterministic applicability/precedence facts and their evidence handles;
- requested comparison and permitted output vocabulary;
- instruction to cite handles, identify alternatives, and abstain when decisive
  evidence is absent.

It excludes raw credentials, environment dumps, executable script bodies,
unrelated resources, complete files when excerpts suffice, and any content not
listed in the disclosure manifest. Secret scanning/redaction is a defense in
depth, not a reason to expand consent.

### 9.2 Neutral response contract

The adapter returns a response envelope with request/input digests, provider and
model identity, provider request ID if safe, adapter and prompt-contract
versions, candidate relations by claim/region/dimension, cited content handles,
reasoning summary, uncertainty/alternatives, and response validation status.
Provider confidence is recorded as provider metadata; local adjudication owns
Agent Doctor confidence.

Missing citations, invalid labels, prompt-echoed secrets, or schema failure make
the response unusable and produce an error/redaction event, not a finding. The
provider never emits an authorization or executable repair.

### 9.3 Manifest authorization and provider policy

Authorization is affirmative and manifest-specific. An explicit one-shot
semantic diagnosis authorizes only the immediately generated manifest; a
standalone invocation requires exact digest confirmation. The record contains
no raw credential and cannot be reused after the provider, content set, purpose,
model, effort, adapter, or prompt contract changes. Provider-side retention,
training, region, and caching behavior are disclosed when knowable; lack of
knowledge is stated, not assumed safe.

Cross-run semantic response caching is off by default. A future opt-in local
cache may be added only if it is disclosed and keyed by provider/model,
adapter/prompt contract, taxonomy, exact minimized input digest, and relevant
policy. It must obey content sensitivity and retention rules, never store raw
credentials, never convert cached inference to proof, and invalidate on any key
change. Physical encryption and retention mechanisms are deferred. Provider-
side caching remains a provider policy fact, not an Agent Doctor guarantee.

## 10. Conceptual versioned result model

The following is a representative structure, not a physical JSON schema or
implementation:

```yaml
result_set:
  schema_version: "agent-doctor-result/0.1"
  result_id: run-scoped-id
  run:
    id: run-id
    started_at: timestamp
    completed_at: timestamp
    outcome: complete | complete_with_gaps | execution_failed
    product_version: version
    taxonomy_version: version
    rule_set_version: version
    normalization_version: version
    platform_profiles: [profile-id@version]
    modes:
      deterministic: enabled
      semantic: enabled | disabled | unavailable
  scope:
    scope_id: stable-digest
    workspace_identity: redacted-or-relative-identity
    selected_regions: [...]
    discovery_boundary: {...}
    inspection_boundary: {...}
    semantic_disclosure_boundary: {...}
    modification_boundary: {...}
    exclusions: [{subject, reason}]
  inventory:
    sources:
      - source_id: stable-logical-id
        type: skill_manifest | skill_body | instruction | override | config | resource
        location: secret-safe-location
        status: discovered | ignored | shadowed | truncated | missing | unreadable | excluded
        revision: fingerprint
        provenance: {...}
  evidence:
    - evidence_id: run-evidence-id
      kind: observed | derived | inferred | runtime
      producer: component-and-version
      source_refs: [...]
      parent_evidence_refs: [...]
      rule_or_provider: {...}
      disclosure: excerpt | location_only | redacted | withheld
  checks:
    - check_id: stable-check-id
      family: check-family
      question: reviewable-proposition
      lifecycle: not_started | started | completed
      state: pass | finding | candidate | insufficient_evidence | not_run | error
      reason: structured-reason
      evidence_refs: [...]
      completeness: complete | partial
  interaction_cases:
    - case_id: stable-case-fingerprint
      check_ref: stable-check-id
      source_refs: [...]
      claim_refs: [...]
      region_ref: region-id
      dimension_ref: dimension-id
      state: one-check-state
      assessments:
        - label: substantive-label
          claim_refs: [...]
          region_ref: region-id
          dimension_ref: dimension-id
      validation_qualifiers:
        - kind: runtime_validation_needed
          proposition: falsifiable-proposition
      severity: critical | high | medium | low | info | null
      potential_severity: critical | high | medium | low | info | null
      confidence: high | medium | low | null
      evidence_refs: [...]
      counterexample: {...}
      next_action_refs: [...]
  finding_groups:
    - group_id: stable-group-fingerprint
      member_case_refs: [...]
      grouping_rule: id@version
      relationship_summary: reviewable-text
  coverage:
    by_family: [{family, attempted, completed, not_run, error, abstained}]
    gaps: [{check_refs, reason, next_action_ref}]
  next_actions: [...]
  diagnostics: [...]
  reproducibility:
    input_revision_manifest: digest
    configuration_digest: digest
    semantic_calls: [{provider, model, contract_version, input_digest, status}]
```

Repair proposals and change records are separate artifacts referencing sealed
result IDs. This prevents a diagnostic result from implying authorization:

```yaml
repair_proposal:
  proposal_id: id
  proposal_digest: digest
  result_ref: sealed-result-id
  selected_case_refs: [...]
  created_from_revisions: [{target, precondition_fingerprint}]
  operations: [{class, target, exact_before, exact_after}]
  rationale: [...]
  expected_effects: [...]
  risks: [...]
  verification_plan: [...]
  rollback_plan: {supported: true, prior_state_requirements: [...]}

authorization_grant:
  grant_id: id
  subject_or_session: bounded-identity
  target_constraints: [...]
  operation_classes: [...]
  valid_from: timestamp
  expires_at_or_session_end: boundary
  proposal_digest: optional-exact-binding
  revoked_at: timestamp-or-null

change_record:
  change_id: id
  proposal_digest: digest
  authorization_ref: grant-or-confirmation-id
  actor_session: id
  apply_state: applied | partially_applied | rejected | conflicted | failed | applied_unverified | verification_failed
  targets: [{target, state, prior_fingerprint, post_fingerprint, verification}]
  prior_state_ref: protected-local-reference
  started_at: timestamp
  completed_at: timestamp
  rollback: {state, record_ref}
```

### 10.1 Projection rules

- Terminal emphasizes scope, highest-impact groups, coverage gaps, and next
  actions, but includes a path to all results.
- Markdown is the durable human review form with inventory, evidence,
  adjudication rationale, versions, and redaction markers.
- JSON preserves the full conceptual graph and machine enums.
- CI evaluates the sealed graph under an explicit policy and reports both its
  outcome and any execution/coverage gaps. Threshold filtering changes the CI
  decision view, not the stored result.
- All projections use the same IDs and axis values. Localized text may differ;
  semantics may not.

## 11. Error handling, partial results, privacy, and security

### 11.1 Error and partial-result rules

- Errors are scoped to the smallest honest diagnostic unit. Independent checks
  continue when their prerequisites remain complete.
- A component diagnostic never silently substitutes a check result. For
  example, a parse failure is recorded as an execution error; a separate
  semantic question that now lacks decisive content may abstain and cite that
  error as the missing prerequisite.
- Retries are bounded and recorded. A transient failure is not called invalid
  until the supported resolver's retry policy is exhausted and the taxonomy
  condition is actually met.
- Partial parser output carries completeness flags. Rules declare required
  prerequisites and cannot treat partial input as complete.
- If the result graph cannot pass invariant validation, it is not advertised as
  a complete canonical result. Available partial diagnostics remain reviewable.

### 11.2 Deduplication and grouping

Candidate cases are normalized by question, logical source/claim identities,
region, dimension, rule, and relevant versions. Exact duplicates collapse into
one case with multiple evidence occurrences. Cases that describe the same user
interaction may form one group, but different states or mutually exclusive
labels are not reconciled by deletion. The group explains whether members are
same defect, causal/related, latent, or dimension-specific. G-004 therefore
produces one duplicate-installation finding; G-018 produces one group with
dimension-qualified redundancy and conflict.

### 11.3 Privacy behavior

- Reports default to workspace-relative, minimized locations and the smallest
  decisive excerpt. Withheld/redacted content is explicitly marked.
- Secrets and raw credentials are excluded from model requests, reports,
  fingerprints that could reveal them, logs, and change records.
- Script bodies are neither executed nor submitted to a model by default.
  Local deterministic inspection of existence/metadata is separate from content
  inspection.
- Full referenced files are not read merely because they are referenced.
  Purpose and scope govern each read.
- Recovery material may necessarily contain sensitive prior content. It is kept
  local, access-limited by the chosen implementation, retention-disclosed, and
  referenced rather than copied into ordinary reports. If it cannot be
  protected adequately, the write type is unsupported.
- User-selected external output may carry disclosed excerpts; the CLI warns at
  the boundary but cannot guarantee the destination's confidentiality.

### 11.4 Security and trust assumptions

Agent Doctor diagnoses coherence, not malware or supply-chain safety. It still
uses defensive parsing, bounded resource use, no script execution, path and
symlink checks, secret minimization, and untrusted-provider validation because
these protect its own contract. Findings must not claim malicious intent from
an escaping reference or unsafe code. Configuration content cannot direct the
scanner, request network access, alter scope, or authorize writes.

## 12. Representative golden-case walkthroughs

| Case | Design path and preserved result |
| --- | --- |
| G-001 | Inventory and parsing preserve mandatory `run`/`do not run` claims. Applicability proves one witness and no resolving precedence. Adjudication assigns `finding`, `scope_overlap` + `semantic_conflict`, high severity/confidence from observed + derived evidence. It does not claim tests were skipped at runtime. |
| G-004 | Discovery records both active occurrences; normalized identifier and structure digest feed the deterministic duplicate rule. Grouper emits one `finding` with all locations, `scope_overlap` + `behavioral_redundancy`, medium/high, without a model or guessed load order. |
| G-006 | The versioned platform profile and complete nested chain derive JSON as the only effective output claim in `repo/api/`. Active-conflict check is `pass` with `precedence_override`, info/high. Latent root text is retained but not mislabeled active conflict; runtime compliance remains unclaimed. |
| G-007 | Peer claims are observed, but the required authority/order rule is absent from the platform/source chain. Precedence question becomes high-confidence `insufficient_evidence`, no winner and no assigned severity; a separately framed conditional latent-conflict candidate is permitted. |
| G-011 | Resolver normalizes `../../private/policy.md`, proves it exits the frozen workspace, and stops before reading it. Deterministic adjudication emits `finding`, `invalid_reference`, medium/high; privacy is preserved and no malicious intent is inferred. |
| G-012 | Inventory count, observed generated list, and a compatible cited 100-entry profile rule derive truncation. Result is `finding`, `context_budget_risk`, medium/high, and records all 12 omitted sources. It makes no future-prompt failure claim. |
| G-015 | Mode configuration prevents semantic-check start, so semantic overlap is `not_run` with no label/severity/confidence. Identity/reference checks complete offline and remain visible. |
| G-016 | The disclosure boundary withholds both bodies. Approved descriptions may support a separately scoped medium-confidence `scope_overlap` candidate with a witness; redundancy/conflict question is `insufficient_evidence`. The content broker cannot silently read or submit the bodies. |
| G-017 | Identical witness triggers and “primary handler” claims create a testable selection-risk hypothesis. With compatible distinct actions and no routing trace/rule, adjudication returns `candidate`, `scope_overlap`, `runtime_validation_needed`, potential medium impact and medium confidence—not conflict or observed misrouting. |
| G-018 | Claims are compared per dimension. One group contains `scope_overlap`, `behavioral_redundancy` on risk-summary output, and `semantic_conflict` on edit/question policy, with `finding`, high/high. Member case/dimension links prevent applying mutually exclusive labels to the same exact relation. |
| G-020 | Inventory succeeds and the validity check starts; the later read failure produces `error` with source, permission/retry evidence, and incomplete coverage. Prior independent findings survive. The architecture cannot turn it into `not_run`, pass, or an invented invalid reference. |

## 13. Traceability

### 13.1 Requirements and acceptance criteria

| Architecture area | PRD requirements | Acceptance criteria | Taxonomy/golden contracts |
| --- | --- | --- | --- |
| Scope presenter, inventory, profiles | P0-R1–R5 | AC-1, AC-3, AC-4 | Diagnostic scope; `precedence_override`; G-006, G-007, G-011, G-019, G-020 |
| Parser, resolver, deterministic engine | P0-R6–R10, P0-R26 | AC-2–AC-4, AC-14 | Duplicate/reference/configuration/budget classes; G-004, G-008, G-010–G-014 |
| Evidence ledger and adjudicator | P0-R11–R15, P1-R1–R6 | AC-3, AC-5–AC-7 | Three axes, evidence kinds, ordered procedure, multi-label and abstention rules; G-001–G-020 |
| Semantic coordinator/provider boundary | P0-R14, P0-R27–R31, P1-R1–R6 | AC-5–AC-7, AC-15–AC-17 | Inferred-evidence rule; `not_run`; `runtime_validation_needed`; G-003, G-015–G-017 |
| Result assembler/renderers/CI | P0-R5, P1-R7–R10 | AC-3, AC-4, AC-7, AC-17 | Stable IDs and versioned future output contract; all cases |
| Repair planner and exact preview | P0-R16–R20, P0-R25 | AC-8–AC-10 | PRD repair boundary; next actions never carry authority |
| Apply, verification, change ledger | P0-R21–R23 | AC-9, AC-12, AC-13 | Evidence/provenance separation and explicit failure states |
| Rollback coordinator | P0-R24 | AC-11–AC-13 | Safe-refusal product principle |
| Content broker/privacy controls | P0-R12, P0-R25–R30 | AC-14–AC-17 | Minimized evidence rules; G-011, G-015, G-016 |

### 13.2 Stage 02 contract preservation

| Contract | Architecture enforcement |
| --- | --- |
| Interaction case is the atomic adjudication unit | `InteractionCase` is keyed by one question, region, and dimension; files are evidence containers, not automatic units. |
| Three independent axes | Separate `state`, `assessments[].label`, and `validation_qualifiers[]` fields validated before result sealing. |
| Deterministic before semantic | Resolvers and deterministic rules precede semantic bundle construction. |
| Shared-region proof | Applicability resolver produces explicit witness/intersection evidence or unknown/empty state. |
| Compare one dimension at a time | Assessment keys include dimension; G-018 grouping remains legal without label collapse. |
| Static/runtime separation | Runtime type exists but has no MVP collector; provider evidence is always inferred; qualifier stores a falsifiable proposition. |
| Counterexample and abstention | Adjudicator requires alternative interpretation and missing-decisive-evidence fields where applicable. |
| Lossless grouping | Groups retain member cases, dimensions, regions, labels, and evidence locations. |

## 14. Architecture decisions and rejected alternatives

| ID | Decision made now | Rejected alternative and rationale |
| --- | --- | --- |
| AD-01 | Preserve check state, substantive assessment, and validation qualifier as independent data. | One overloaded issue enum cannot represent G-015/G-018 and invites not-run-as-pass errors. |
| AD-02 | Use one sealed result graph for all projections. | Independent renderer analysis would violate AC-4 and create inconsistent findings. |
| AD-03 | Represent platform behavior in versioned, attributable profiles. | Silent hard-coded discovery/precedence/budget assumptions become stale and falsely deterministic. |
| AD-04 | Use immutable typed evidence with lineage. | Free-form explanations cannot prove which facts were observed, derived, or inferred. |
| AD-05 | Complete deterministic analysis without provider dependencies. | A model-required core would violate offline and degraded-mode requirements. |
| AD-06 | Bind semantic use to an exact disclosure manifest, use two blind parallel analysts plus a fresh judge, and treat all outputs as inferred. | Blanket authorization, single-pass opinions, and provider-direct findings violate minimization, stability, and evidence rules. |
| AD-07 | Centralize taxonomy adjudication after rule/provider evidence production. | Letting each detector invent final semantics creates inconsistent abstention and multi-label behavior. |
| AD-08 | Separate repair proposal, authorization, apply, and rollback artifacts; bind confirmation to proposal digest. | A mutable plan or “fix selected findings” grant could silently expand writes. |
| AD-09 | Use optimistic compare-before-write with source revision, identity, and path preconditions plus recorded post-images. | Blind writes or path-only checks can overwrite concurrent work or swapped targets. |
| AD-10 | Preflight all rollback targets against recorded post-images and refuse the whole rollback on mismatch. | Best-effort overwrite/merge cannot guarantee restoration without damaging unrelated changes. |
| AD-11 | Disable cross-run semantic cache by default; permit only later explicit, policy-keyed opt-in caching. | Implicit caching weakens disclosure, retention, reproducibility, and inference freshness. |
| AD-12 | Make grouping versioned and lossless. | Alert suppression by text similarity can erase different dimensions or evidence gaps. |
| AD-13 | Keep recovery material separate from ordinary reports and require protectable prior state for supported writes. | Embedding prior content in reports leaks secrets; claiming rollback without state is unsafe. |
| AD-14 | Use an allowlist of reversible repair operation classes. | Generic arbitrary file editing cannot satisfy bounded authorization and rollback claims. |

### 14.1 Implementation choices intentionally deferred

Stage 05 may choose among implementations only after preserving these decisions.
In particular, this design does not decide:

- programming language, package layout, dependency injection, or concurrency
  model;
- YAML/JSON/database physical storage for profiles, results, or the ledger;
- concrete hash, canonical serialization, lock, file replacement, or backup
  primitive;
- exact supported Codex paths and limits until attributable profiles are
  reviewed;
- first repair operation classes and OS/filesystem coverage;
- provider list, model-selection policy, prompt wording, retry counts, or local
  cache storage;
- numeric process exit codes and Stage 04 blocking thresholds;
- retention periods and integration with an OS credential/protected storage
  facility.

Deferral is not permission to weaken a contract. For example, any chosen hash
and serialization must make proposal/revision comparison stable; any chosen
storage must keep secrets out of ordinary reports; any chosen exit codes must
distinguish policy failure from execution failure.

## 15. Internal architecture review

The 2026-08-17 documentation review checked the following before handoff:

- **Consistency:** state/label/qualifier remain separate in entities, contracts,
  flows, schema, renderers, and golden walkthroughs. Override, abstention,
  not-run, error, and runtime-candidate boundaries match Stage 02.
- **Traceability:** every P0 requirement, P1 diagnostic/reporting requirement,
  AC-1–AC-17, and all required representative golden cases map to a component
  or decision. Product thresholds are referenced without claiming attainment.
- **Privacy:** local deterministic mode has no provider dependency; disclosure
  is content- and provider-specific; secrets, scripts, escaping references,
  recovery content, and outputs each have explicit boundaries.
- **Failure modes:** unavailable versus attempted failure versus missing
  decisive evidence are distinct; partial results, renderer failure, CI policy
  failure, partial apply, verification failure, expiry/revocation, path change,
  and rollback conflict have explicit states.
- **Repair safety:** analysis, model consent, proposal selection, and
  authorization are non-substitutable; exact preview, digest binding, all-target
  preflight, prior/post capture, at-most-once behavior, verification, and safe
  rollback refusal are present.
- **Scope:** no product implementation code, Stage 04 fixture/scoring protocol,
  Stage 05 technology selection, runtime collection, security-scanner promise,
  or non-Codex platform support was introduced.

### 15.1 Review assumptions carried forward

1. Stage 04 must turn these contracts into scenario matrices and executable
   fixtures; this document does not assert measured precision or recall.
2. Stage 05 must materialize at least one reviewed platform profile before a
   version-dependent deterministic rule can ship.
3. A repair type is not supported until its target identity, exact operation,
   preconditions, prior-state protection, verification, and rollback behavior
   are all implemented and tested.
4. Runtime evidence remains a reserved provenance type only. Introducing a
   producer requires a later approved scope and privacy design.
5. The English document is canonical. The Chinese copy is complete for review;
   disagreements are resolved against this document unless the canonical text
   is amended.
