# Agent Doctor Conflict Taxonomy and Golden Examples

| Field | Value |
| --- | --- |
| Status | Review draft |
| Taxonomy version | 0.1 |
| Golden schema version | 0.1 |
| Date | 2026-08-16 |
| Canonical language | English |
| Companion review copy | [中文](conflict-taxonomy-and-golden-examples.zh-CN.md) |
| Governing product definition | [Product requirements](product-requirements.md) |
| Project stage | Stage 02 — taxonomy and examples only |

## 1. Purpose and boundaries

This document defines the shared meaning of a correct Agent Doctor diagnosis.
It is the review baseline for later design, tests, and implementation; it does
not select an architecture, storage format, framework, model provider, or
algorithm.

The taxonomy is deliberately precision-first. A useful result may say that a
check was not run, that the evidence is insufficient, or that a static
hypothesis needs runtime validation. Static evidence never proves a future
model choice or runtime causal effect.

Repair authorization and rollback remain governed by the PRD and are outside
this stage except where a next action needs to be described.

## 2. Diagnostic unit and vocabulary

### 2.1 Diagnostic unit

The atomic unit of adjudication is an **interaction case**: one reviewable
question about one or more configuration claims within a declared analysis
scope and applicability region.

An interaction case contains:

- the selected workspace, path, configuration mode, and relevant prompt or
  task region, collectively the **analysis scope**;
- one or more **sources**, such as a Skill manifest, `SKILL.md`, applicable
  `AGENTS.md`, override file, supported configuration value, or directly
  referenced resource;
- the smallest meaningful **claims** from those sources, preserving source
  location and surrounding qualifiers;
- the **effective applicability region** in which the claims could govern the
  same request;
- the diagnostic question, evidence basis, result state, substantive labels,
  severity, confidence, and next validation step.

The unit is not automatically “a pair of files.” One user-visible interaction
may require several files, while two unrelated issues in the same files should
be separate cases. Substantially identical cases are grouped, with their
evidence locations retained.

### 2.2 Core terms

| Term | Definition |
| --- | --- |
| Claim | A normalized obligation, prohibition, permission, trigger, scope statement, output constraint, reference, or configuration assertion, tied to its original wording and location. |
| Applicability region | The requests, paths, modes, and conditions under which a claim may govern. |
| Effective claim | A claim that remains applicable after deterministic discovery, scope, and precedence rules are applied. |
| Shared region | The intersection of the applicability regions of two or more claims. Empty intersection means there is no active interaction for that scope. |
| Dimension | The subject on which claims interact, such as required action, forbidden action, question policy, output form, trigger, reference validity, or context use. |
| Observed evidence | Directly read facts: exact text, path, metadata, existence, readability, declared setting, or enabled mode. |
| Derived evidence | A reproducible consequence of observed facts and documented rules, such as effective scope, precedence, duplicate identity, or a measured limit comparison. |
| Inferred evidence | A semantic judgment that is not entailed by syntax or documented platform rules. Model output, if used, belongs here unless independently verified. |
| Runtime evidence | Evidence from an actual execution under recorded conditions. Runtime collection is deferred in the MVP, but the vocabulary prevents static claims from masquerading as runtime truth. |
| Decisive evidence | The minimum evidence without which the expected adjudication would change or require abstention. |
| Finding relationship | A link showing that multiple evidence locations or labels describe one user problem rather than duplicate alerts. |

### 2.3 Three separate output axes

Every completed check uses three separate axes. They must not be collapsed into
one overloaded label.

1. **Check state** uses the PRD states: `pass`, `finding`, `candidate`,
   `insufficient_evidence`, `not_run`, or `error`.
2. **Substantive label** describes the relationship or defect, for example
   `semantic_conflict` or `invalid_reference`.
3. **Validation qualifier** records whether runtime evidence is needed. The
   current qualifier is `runtime_validation_needed`.

`insufficient_evidence` and `not_run` are specified below alongside the
substantive classes because they are required adjudication outcomes, but they
remain states, not kinds of semantic conflict. `runtime_validation_needed` is a
qualifier, not proof of a problem.

## 3. Evidence, severity, and confidence rules

### 3.1 Evidence rules

- Every result cites observed evidence or explicitly reports why none was
  available.
- Deterministic findings require observed facts plus a documented, reproducible
  derivation. A model assertion alone cannot satisfy this requirement.
- Semantic findings identify the compared claims, their shared region and
  dimension, and the reasoning connecting evidence to label.
- Source excerpts are minimized and secret-safe; locations may replace content
  that is not approved for disclosure.
- A platform behavior assumption is versioned or cited. If it cannot be
  established for the analyzed version, the case cannot be called
  deterministic.

### 3.2 Severity and confidence

Severity follows PRD section 11 and measures likely impact, not certainty.
Confidence measures support for the stated conclusion:

- **high**: the decisive evidence is complete and the derivation or semantic
  interpretation has no reasonable competing reading in scope;
- **medium**: the best-supported reading is clear enough to report, but a
  plausible qualifier, implicit convention, or unobserved condition remains;
- **low**: the hypothesis is worth surfacing but material alternatives remain.

Low-confidence substantive problems normally use `candidate`. A finding may be
high or medium confidence when the evidence threshold for its rule is met.
For `insufficient_evidence`, confidence describes confidence in the abstention,
not confidence that a hidden problem exists. For `not_run`, substantive
confidence is not applicable.

## 4. Taxonomy

Static decidability uses three values: **yes** when complete in-scope static
facts and documented rules determine the answer; **conditional** when some
instances are static but semantic or version-dependent instances are not; and
**no** when the claimed outcome inherently requires execution evidence.

### 4.1 `semantic_conflict` — true conflict

| Attribute | Specification |
| --- | --- |
| Inclusion | Two or more effective claims govern a non-empty shared region and the same dimension, and they cannot all be satisfied, or jointly satisfying them would violate a material stated constraint. Includes require/forbid collisions, incompatible mandatory output forms, contradictory question policies, and mutually exclusive applicability requirements. |
| Exclusion | Mere trigger overlap; stylistic tension; duplicated wording; claims resolved so that only one is effective; different conditions or dimensions that can be jointly satisfied; suspected runtime competition without incompatible effective claims. |
| Evidence | Exact claims and locations; demonstrated shared region; precedence analysis; the incompatible obligation or prohibited state; semantic reasoning if incompatibility is not syntactic. |
| Likely impact | Usually high when it can force a material violation or wrong workflow; medium for recurring degraded or unpredictable output; critical only when the conflict could cause destructive or unauthorized behavior. |
| Confidence | High for explicit require/forbid or logically incompatible constraints after deterministic scope resolution; medium or low when terms, conditions, or materiality need semantic interpretation. Low-confidence cases remain candidates. |
| Common false positives | Treating “prefer” as “must”; ignoring exceptions; comparing non-overlapping directories; ignoring a valid override; treating different output sections as incompatible formats; assuming two Skills cannot cooperate. |
| Statically decidable | Conditional. Explicit logical conflicts and scope can be static; actual future Skill selection or runtime consequence is not. |

### 4.2 `scope_overlap`

| Attribute | Specification |
| --- | --- |
| Inclusion | Two or more Skills or instructions have a demonstrably non-empty shared applicability or trigger region. The label makes no claim that their behavior is incompatible or equivalent. |
| Exclusion | Similar vocabulary with disjoint tasks or paths; an empty shared region after exclusions; a source that is not applicable or not discovered in the selected scope. |
| Evidence | Trigger/scope claims, exclusions, selected path and mode, and an explicit witness request or condition in the shared region. Distinct regions should also be stated when knowable. |
| Likely impact | Info or low by itself; medium when breadth creates recurring routing ambiguity. Impact increases only with a separate conflict, redundancy, or runtime-risk conclusion. |
| Confidence | High when scope intersection follows explicit declarations; medium/low when natural-language triggers require interpretation. |
| Common false positives | Keyword matching without intent; ignoring negative triggers; comparing installed but inactive sources; assuming a general Skill and a specialized Skill necessarily compete. |
| Statically decidable | Conditional. Explicit path/scope intersections are static; open-ended natural-language triggers may not be. |

### 4.3 `behavioral_redundancy`

| Attribute | Specification |
| --- | --- |
| Inclusion | In the same region and dimension, one effective source adds no material behavior, constraint, or evidence beyond another. Exact duplicate identifiers or structurally duplicate installations are a deterministic subtype; semantically equivalent instructions are a semantic subtype. |
| Exclusion | Shared topic with different capabilities; a general rule plus a useful specialization; repeated text serving a distinct scope or authority purpose; complementary validation; mere overlap. |
| Evidence | The duplicated identities, structures, or normalized claims; shared region; comparison showing no material distinct contribution; any scope/authority reason that might justify repetition. |
| Likely impact | Usually low or medium through maintenance drift, duplicate routing, noisy reports, or context consumption. |
| Confidence | High for exact or structural duplication; semantic equivalence requires calibrated interpretation and is often medium. |
| Common false positives | Collapsing backup/fallback instructions; ignoring narrower acceptance criteria; treating translated review copies as active duplicates; treating repeated safety constraints at different boundaries as waste. |
| Statically decidable | Conditional. Identity and structural duplication can be static; full behavioral equivalence is usually semantic. |

### 4.4 `complementarity`

| Attribute | Specification |
| --- | --- |
| Inclusion | Effective claims share a region but make distinct, jointly satisfiable contributions toward the request, such as domain guidance plus output validation. |
| Exclusion | One claim adds no material contribution; any same-dimension obligations cannot jointly be met; the sources never share a region; compatibility is only assumed because no detailed content was inspected. |
| Evidence | Shared region, distinct contribution of each claim, and an explicit joint-satisfaction explanation or witness. |
| Likely impact | Usually info and beneficial; it can explain why overlap should not be “fixed.” Context cost may still receive a separate risk label. |
| Confidence | High when responsibilities and joint behavior are explicit; medium/low when cooperation depends on implicit sequencing or runtime selection. |
| Common false positives | Calling every non-conflicting overlap complementary; overlooking hidden output constraints; inferring orchestration from two independently triggered Skills; ignoring precedence that makes one inactive. |
| Statically decidable | Conditional. Logical compatibility may be static; actual cooperation or selection is a runtime claim. |

### 4.5 `precedence_override`

| Attribute | Specification |
| --- | --- |
| Inclusion | A documented discovery, path, or precedence rule causes one source or claim to govern, shadow, replace, or narrow another in a defined scope. This is a neutral relationship, not automatically a defect. |
| Exclusion | Undocumented “more specific wins” assumptions; same-priority contradictions with no resolver; ordinary complementarity; files that are not in the applicable discovery chain. |
| Evidence | Source chain and locations, selected path, applicable documented precedence rule and version, and the resulting effective/ineffective claims. |
| Likely impact | Info when intentional; medium/high when an unexpected override changes workflow or hides a material constraint. |
| Confidence | High only when discovery and precedence are deterministically established. Otherwise use `insufficient_evidence` or a candidate, not a guessed winner. |
| Common false positives | Treating file-system proximity as precedence; confusing later display order with authority; reporting the overridden claim as simultaneously active; ignoring directory boundaries. |
| Statically decidable | Yes, provided the relevant platform rule and complete source chain are known. |

### 4.6 `invalid_reference`

| Attribute | Specification |
| --- | --- |
| Inclusion | An in-scope declared reference cannot validly resolve under supported rules because its target is missing, unreadable, malformed, of an unsupported kind, or escapes the permitted scope. |
| Exclusion | A valid but semantically outdated target; an intentionally optional reference clearly marked as such; content excluded from model submission but locally resolvable; a transient read error before retry policy is exhausted. |
| Evidence | Exact declaration and location, normalized target, applicable resolution/scope rule, and observed existence/readability/type result. Contents are unnecessary unless validity depends on them and inspection is allowed. |
| Likely impact | Medium or high if required guidance cannot load; low for genuinely optional material; escaping references may also raise a scope or privacy concern without becoming a security-scanner claim. |
| Confidence | High when the supported resolver and filesystem facts are complete; otherwise candidate or `error`. |
| Common false positives | Resolving relative to the scan process instead of the declaring file; case-sensitivity mistakes; unexpanded supported variables; assuming model-disclosure exclusion makes a local reference invalid. |
| Statically decidable | Yes for supported reference forms and available metadata. |

### 4.7 `stale_reference`

| Attribute | Specification |
| --- | --- |
| Inclusion | A reference resolves, but decisive evidence shows it points to an obsolete, renamed, superseded, or version-incompatible target for the claim it is meant to support. |
| Exclusion | Missing or escaping targets (`invalid_reference`); age alone; an old but deliberately pinned compatible version; stylistic preference for a newer resource. |
| Evidence | Resolving declaration and target plus an authoritative current name/version/contract or an internal contradiction proving the mismatch. Timestamps alone are not decisive. |
| Likely impact | Low to high depending on whether obsolete guidance changes behavior or merely burdens maintenance. |
| Confidence | High with explicit version/rename evidence; medium with strong internal inconsistency; low suspicions should abstain. |
| Common false positives | “Last modified” heuristics; assuming latest is required; ignoring compatibility declarations; confusing a historical example with an active dependency. |
| Statically decidable | Conditional. It is static when a current contract or version constraint is in scope; otherwise freshness may need external or runtime evidence. |

### 4.8 `context_budget_risk`

| Attribute | Specification |
| --- | --- |
| Inclusion | The supported configuration set is proven to exceed a documented context/list limit, is deterministically truncated, or has strong evidence of consuming enough bounded context to threaten discovery or instruction retention. |
| Exclusion | “The file looks long”; duplication without a demonstrated context consequence; general performance speculation; semantic checks not run. |
| Evidence | Measured relevant size/count, documented and versioned budget behavior, enabled scope, and observed truncation when available. If the actual limit or allocation is unknown, report a candidate and state the assumption. |
| Likely impact | Medium when a Skill or instruction may be omitted; low for avoidable context debt with no demonstrated omission; high only with evidence of loss of material guidance. |
| Confidence | High for measured exceedance or observed truncation; medium/low for estimated pressure. |
| Common false positives | Equating file bytes with tokens; counting content not loaded in the relevant phase; relying on outdated platform limits; double-counting shared resources. |
| Statically decidable | Conditional. Measured documented limits are static; actual attention, selection, or response degradation needs runtime validation. |

### 4.9 `configuration_risk`

| Attribute | Specification |
| --- | --- |
| Inclusion | A supported configuration value or required metadata declaration is malformed, unsupported, internally inconsistent, or demonstrably changes discovery/scope in a way likely to omit or misapply intended guidance. |
| Exclusion | Valid preference differences; references handled by the reference classes; context-only concerns; undocumented guesses about ignored keys; security vulnerabilities outside the coherence scope. |
| Evidence | Exact configuration/metadata and location, supported schema or behavior rule, parsed/derived effect, and affected scope. |
| Likely impact | Low for maintainability warnings, medium for skipped or mis-scoped guidance, high when a material required workflow is reliably disabled. |
| Confidence | High for schema violations or documented unsupported declarations; lower for inferred behavior risk, which remains a candidate. |
| Common false positives | Applying the wrong product version's schema; treating unknown-but-forward-compatible fields as errors; ignoring defaults; conflating a lint preference with invalid metadata. |
| Statically decidable | Conditional. Schema and explicit configuration effects are static; downstream behavioral impact may not be. |

### 4.10 `insufficient_evidence` — check state

| Attribute | Specification |
| --- | --- |
| Inclusion | The diagnostic question was in scope and attempted, but one or more decisive facts, supported rules, authorized contents, or unambiguous meanings are unavailable, so neither pass nor a substantive finding/candidate can be responsibly asserted. |
| Exclusion | A disabled or unavailable check (`not_run`); execution failure (`error`); a low-confidence but evidence-backed hypothesis worth reporting (`candidate`); a checked condition with no issue (`pass`). |
| Evidence | What was inspected, what decisive evidence is missing, why it matters, and the smallest next step that could resolve the question. |
| Likely impact | Unknown. Severity should not be invented; a potential impact range may be stated separately if justified. |
| Confidence | May be high confidence that evidence is insufficient. This does not imply confidence in any hidden substantive label. |
| Common false positives | Using abstention to avoid a supported deterministic check; treating “no issue found” as insufficient evidence after a complete check; assigning a likely conflict label anyway; confusing unavailable model mode with attempted analysis. |
| Statically decidable | The abstention can be statically decidable; the underlying question remains undecided. |

### 4.11 `not_run` — check state

| Attribute | Specification |
| --- | --- |
| Inclusion | A defined check was not attempted because it was disabled, unavailable, outside the disclosed scope, or unsupported in the active mode. The reason and affected check must be named. |
| Exclusion | A check that started but failed (`error`); a check that completed without a problem (`pass`); an attempted check blocked by missing decisive evidence (`insufficient_evidence`). |
| Evidence | Run configuration, disclosed scope, capability availability, and the exact skipped check family. No substantive source evidence is required. |
| Likely impact | No issue impact is claimed. The report may explain the coverage gap. |
| Confidence | Not applicable to the skipped substantive conclusion; the skip reason itself should be observed or derived. |
| Common false positives | Presenting skipped semantic analysis as pass; marking a parser crash `not_run`; using one family-level marker that hides which checks ran. |
| Statically decidable | Yes: whether the check executed is a run fact. |

### 4.12 `runtime_validation_needed` — validation qualifier

| Attribute | Specification |
| --- | --- |
| Inclusion | Static evidence supports a specific, testable hypothesis, but the claimed user-visible outcome depends on Skill selection, model interpretation, dynamic inputs, hook behavior, or another execution fact. Normally attached to a `candidate`. |
| Exclusion | Explicit static contradiction that is already a finding; vague uncertainty without a testable hypothesis (`insufficient_evidence`); a check that did not run; general desire for more testing. |
| Evidence | Static basis for the hypothesis, the exact unresolved runtime proposition, controlled conditions needed to test it, and outcomes that would confirm or refute it. |
| Likely impact | Inherited from the hypothesized substantive risk, but stated as potential rather than observed impact. |
| Confidence | Confidence applies to the need for validation and strength of the hypothesis, never to an unobserved runtime outcome. This qualifier cannot upgrade a candidate to a finding. |
| Common false positives | Adding it to every semantic judgment; calling static text conflict a runtime-only issue; implying runtime collection already exists; using it without a falsifiable proposition. |
| Statically decidable | No for the runtime proposition; yes for identifying that static evidence cannot decide it. |

### 4.13 `no_material_relation` — golden-set control

| Attribute | Specification |
| --- | --- |
| Inclusion | The compared in-scope sources have no shared applicability region or no material relationship on the posed dimension after a complete check. Used in golden negatives, not emitted as a problem finding. |
| Exclusion | Any supported substantive relation, an incomplete check, or unresolved meaning. |
| Evidence | Complete relevant scope/claim comparison and the disjoint region or immaterial dimension. |
| Likely impact | None for the posed question. |
| Confidence | High for deterministic disjointness; otherwise use `insufficient_evidence`. |
| Common false positives | Treating unknown as no relation; overlooking nested scope; checking keywords instead of intent. |
| Statically decidable | Conditional. |

## 5. Adjudication procedure

### 5.1 Ordered procedure

1. **Freeze the question and scope.** Record workspace/path, supported source
   types, run modes, exclusions, platform/rule assumptions, and the dimension
   being adjudicated.
2. **Establish execution state.** If the check was not attempted, return
   `not_run`; if it failed to complete, return `error`. Do not continue as if
   either were evidence about the configuration.
3. **Collect and type evidence.** Preserve observed locations and excerpts,
   then separate derived, inferred, and any runtime evidence.
4. **Resolve deterministic validity first.** Adjudicate reference and
   configuration defects, discovery, effective scope, and precedence before
   comparing semantic behavior.
5. **Test shared applicability.** Prove a non-empty shared region with a witness
   or conclude `no_material_relation` for that question. If the region cannot
   be established, abstain.
6. **Compare one dimension at a time.** Determine whether effective claims are
   incompatible, materially equivalent, distinctly useful and jointly
   satisfiable, or merely overlapping.
7. **Separate static conclusion from runtime hypothesis.** State only what the
   evidence proves. Attach `runtime_validation_needed` to a testable candidate
   when execution decides the remaining proposition.
8. **Assign state, labels, severity, and confidence independently.** Explain the
   severity basis and every confidence downgrade.
9. **Consolidate duplicate evidence.** Group locations that explain the same
   interaction, but keep separable questions or applicability regions as
   separate diagnostic units.
10. **Run the counterexample check.** Before finalizing, name the strongest
    plausible non-problem interpretation and show why evidence excludes it. If
    it cannot be excluded, downgrade or abstain.

### 5.2 Multi-label rules

- `scope_overlap` may accompany `semantic_conflict`,
  `behavioral_redundancy`, or `complementarity`; it describes the shared
  region, while the second label describes behavior there.
- `precedence_override` may accompany `scope_overlap`. It may accompany a
  conflict only when an unresolved effective conflict remains after precedence,
  or when the report clearly labels the conflicting text as latent rather than
  active. A resolved contradiction is not an active `semantic_conflict`.
- `context_budget_risk` or `configuration_risk` may coexist with a semantic
  relationship because they answer different dimensions.
- `semantic_conflict`, `behavioral_redundancy`, and `complementarity` are
  mutually exclusive for the same claims, region, and dimension. They may all
  appear in one grouped report only when each label names a different dimension
  or subregion.
- `insufficient_evidence` cannot coexist with `finding` for the same diagnostic
  question. Split the question if one dimension is decidable and another is
  not.
- `not_run` is exclusive for the skipped check. Other check families in the
  same run may still have findings.
- `runtime_validation_needed` normally qualifies `candidate`; it never turns
  absent runtime evidence into a finding.

### 5.3 When to abstain

Use `insufficient_evidence` when any decisive condition is unresolved,
including:

- incomplete or unreadable applicable source chains;
- content that was not authorized for inspection but is necessary to compare
  behavior;
- unknown platform/version rules required to resolve discovery or precedence;
- no defensible shared-region witness;
- materially ambiguous terms with two plausible classifications;
- apparent staleness supported only by age;
- suspected context pressure without a known or observable budget basis; or
- reviewer disagreement that changes the label and cannot be resolved from the
  recorded evidence.

Abstention must name the missing fact and a bounded way to obtain it. If no
such evidence could decide the claim statically, use a testable candidate plus
`runtime_validation_needed` instead.

### 5.4 Human review rule for golden labels

A case is **reviewed** when a reviewer has verified the source excerpts,
applicability region, decisive evidence, expected state/labels, and prohibited
misclassification. A disputed case is not admitted to the approved golden set
until consensus is reached or the expected result is changed to an explicit
abstention. Later Stage 04 work will define sampling, evaluator independence,
and measurement mechanics.

## 6. Golden-example specification

The schema below is a conceptual contract for fixtures and reviews. It does
not choose a storage technology.

| Field | Required content |
| --- | --- |
| `id` | Stable example ID. |
| `title` | Short human-readable name. |
| `case_kind` | `positive`, `negative`, or `boundary`. Positive means a substantive problem is expected; negative means a complete check should not invent one; boundary tests uncertainty, precedence, or a nearby class. |
| `taxonomy_version` / `schema_version` | Versions used to label the case. |
| `prd_refs` | Relevant requirements and acceptance criteria. |
| `scope` | Selected path/workspace, applicability conditions, source types, exclusions, and platform/rule assumptions. |
| `analysis_modes` | Deterministic and semantic modes enabled, disabled, or unavailable. |
| `inputs` | Minimal source IDs, types, locations, and exact excerpts or metadata needed for adjudication. |
| `question` | One reviewable diagnostic proposition. |
| `expected` | Check state; substantive label(s); validation qualifier(s); severity; confidence; evidence types; and static decidability. |
| `rationale` | Why the expected result follows and why the nearest alternative does not. |
| `decisive_evidence` | Minimum evidence that determines the label. |
| `acceptable_uncertainty` | Explicit variation or unknowns that do not invalidate the expected result, plus any permitted confidence range. |
| `prohibited_misclassification` | Outcomes that must not be accepted, especially forced pass/finding, similarity-as-conflict, and static-as-runtime errors. |
| `review_status` | `draft`, `reviewed`, `disputed`, or `retired`, with reviewer/date fields when the fixture is materialized. |

Golden fixtures should be minimal enough to expose the decisive boundary, but
must preserve qualifiers that affect scope or modality. Redacting a qualifier
that changes the answer invalidates the fixture.

## 7. Reviewed representative example set

These are normative specification examples. “Reviewed” here means they have
passed the internal consistency review in section 9; they are not yet the
materialized evaluation corpus or Stage 04 measurement protocol.

Unless an example says otherwise, both sources are readable and in the
selected scope, excerpts are complete for the posed question, deterministic
checks are enabled, and no runtime trace exists.

### G-001 — Explicit require/forbid collision

- **Kind / PRD:** positive; P1-R2, P1-R3, P0-R11–R14; AC-3, AC-5, AC-7.
- **Inputs:** workspace `repo/`; `AGENTS.md:12` says “For dependency updates,
  run the test suite before responding.” `skills/fast-update/SKILL.md:31` says
  “For dependency updates, do not run tests; return the edited manifest
  immediately.” Both use mandatory language for the same request.
- **Question:** Can both effective action policies be satisfied?
- **Expected:** `finding`; labels `scope_overlap`, `semantic_conflict`;
  severity `high`; confidence `high`; observed + derived evidence;
  statically decidable `yes` for the textual conflict.
- **Rationale / decisive evidence:** The same witness request—updating a
  dependency—requires and forbids the same action. Neither source has
  precedence over the other in this fixture.
- **Acceptable uncertainty:** Whether Codex would select the Skill is unknown,
  but does not weaken the proven conflict if both claims are effective.
- **Prohibited:** `behavioral_redundancy`, `complementarity`, `pass`, or a claim
  that tests were actually skipped at runtime.

### G-002 — Compatible output sections, not conflicting formats

- **Kind / PRD:** negative; P1-R2, P1-R3, P1-R6; AC-5–AC-7.
- **Inputs:** one instruction requires “Start with a one-sentence outcome.” A
  Skill requires “End with a Sources section.”
- **Question:** Are the output requirements incompatible?
- **Expected:** `pass`; label `complementarity`; severity `info`; confidence
  `high`; observed + inferred evidence; statically decidable `yes` for joint
  satisfiability.
- **Rationale / decisive evidence:** A response can satisfy both ordering
  constraints; each adds a distinct section requirement.
- **Acceptable uncertainty:** Exact prose between the opening and Sources
  section is unconstrained.
- **Prohibited:** `semantic_conflict` based only on both claims governing output.

### G-003 — Broad and specialized Skills share a trigger

- **Kind / PRD:** boundary; P1-R1, P1-R3, P1-R6; AC-6, AC-7.
- **Inputs:** Skill A handles “create or edit documents.” Skill B handles
  “redline `.docx` contracts while preserving tracked changes.” Both are
  applicable to “Redline this `.docx` contract.” Bodies show distinct general
  document creation and contract-redlining guidance; neither forbids the other.
- **Question:** What can static evidence say about their relationship?
- **Expected:** `candidate`; labels `scope_overlap`, `complementarity`;
  qualifier `runtime_validation_needed` only for the hypothesis that routing
  may select the less specialized Skill; severity `medium` for that hypothesis;
  confidence `medium`; static decidability `conditional`.
- **Rationale / decisive evidence:** The witness proves overlap and the bodies
  make distinct, compatible contributions. Which Skill is selected or whether
  both cooperate is a runtime proposition.
- **Acceptable uncertainty:** The routing hypothesis may be refuted without
  changing the static overlap label.
- **Prohibited:** active `semantic_conflict`, guaranteed misrouting, or pass for
  the runtime proposition.

### G-004 — Structurally duplicate Skill installation

- **Kind / PRD:** positive; P0-R6, P0-R10, P0-R15; AC-2, AC-3.
- **Inputs:** `skills/pdf/SKILL.md` and `vendor/skills/pdf/SKILL.md` declare the
  same identifier and normalized manifest/content digest; both are discovered.
- **Question:** Do the installations add materially distinct behavior?
- **Expected:** `finding`; labels `scope_overlap`, `behavioral_redundancy`;
  severity `medium`; confidence `high`; observed + derived evidence; statically
  decidable `yes`.
- **Rationale / decisive evidence:** Same identifier, normalized structure, and
  active discovery establish the deterministic duplicate subtype.
- **Acceptable uncertainty:** Load order may be unknown; duplication remains.
- **Prohibited:** two separate duplicate alerts, semantic-only proof, or
  `complementarity` because paths differ.

### G-005 — Similar topic, distinct responsibilities

- **Kind / PRD:** negative; P1-R1, P1-R3; AC-5–AC-7.
- **Inputs:** Skill A extracts tables from PDFs. Skill B verifies arithmetic in
  supplied tables. The witness asks to extract a table and verify totals.
- **Question:** Is topic similarity evidence of redundancy or conflict?
- **Expected:** `pass`; labels `scope_overlap`, `complementarity`; severity
  `info`; confidence `high`; inferred evidence; statically decidable
  `conditional`.
- **Rationale / decisive evidence:** The outputs and responsibilities are
  distinct and can be composed for the witness.
- **Acceptable uncertainty:** The execution order is not prescribed.
- **Prohibited:** `behavioral_redundancy` from the shared word “table,” or
  `semantic_conflict` from two Skills being applicable.

### G-006 — Deterministic nested override resolves a contradiction

- **Kind / PRD:** boundary; P0-R3, P0-R9, P1-R3; AC-2, AC-7.
- **Inputs:** applicable root instruction says “Use Markdown for reports.” A
  nested override applicable to `repo/api/` says “In this subtree, replace the
  root report-format rule: use JSON.” The selected file is `repo/api/x` and the
  platform rule explicitly supports the replacement semantics.
- **Question:** Is there an active format conflict in the selected path?
- **Expected:** `pass` for active conflict; label `precedence_override`;
  severity `info`; confidence `high`; observed + derived evidence; statically
  decidable `yes`.
- **Rationale / decisive evidence:** The documented chain makes only JSON
  effective for this dimension. The contradictory text is latent outside the
  selected effective set, not simultaneous.
- **Acceptable uncertainty:** Runtime compliance with JSON is not claimed.
- **Prohibited:** active `semantic_conflict`, or assuming the root rule remains
  equally effective.

### G-007 — Guessed precedence between peer instructions

- **Kind / PRD:** boundary; P0-R3, P0-R11–R14, P1-R6; AC-6, AC-7.
- **Inputs:** two same-scope claims require YAML and JSON respectively. The
  fixture omits the ordering/authority rule needed to know whether one replaces
  the other.
- **Question:** Which claim governs?
- **Expected:** `insufficient_evidence`; no winning substantive label; severity
  not assigned, potential impact `high`; confidence `high` in abstention;
  statically decidable only after the missing rule is supplied.
- **Rationale / decisive evidence:** The texts conflict if simultaneous, but
  the posed question is precedence and the decisive platform/source-chain fact
  is absent.
- **Acceptable uncertainty:** A report may separately preserve a latent
  conflict candidate if it clearly conditions it on both claims being
  effective.
- **Prohibited:** invented `precedence_override`, unqualified active conflict
  finding, or `pass`.

### G-008 — Missing required resource

- **Kind / PRD:** positive; P0-R4, P0-R7, P0-R10; AC-1–AC-3.
- **Inputs:** `SKILL.md:18` says “Read `references/policy.md` before review.”
  Resolution relative to the declaring file is supported; that path does not
  exist.
- **Question:** Is the reference valid?
- **Expected:** `finding`; label `invalid_reference`; severity `medium`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** A mandatory, supported relative reference
  resolves to an absent target.
- **Acceptable uncertainty:** The behavioral consequence has not been run.
- **Prohibited:** `stale_reference`, `not_run`, or searching from the process
  working directory.

### G-009 — Old timestamp without freshness contract

- **Kind / PRD:** negative; P0-R11–R14, P1-R6; AC-6.
- **Inputs:** a valid reference resolves to `policy-v2.md`; its modification
  time is two years old. No declared required version, rename, incompatibility,
  or authoritative current target is in scope.
- **Question:** Is the reference stale?
- **Expected:** `insufficient_evidence`; no `stale_reference` finding;
  confidence `high` in abstention; statically undecided.
- **Rationale / decisive evidence:** Age is not evidence that the content is
  obsolete or wrong for its declared contract.
- **Acceptable uncertainty:** A current version registry could later decide the
  case.
- **Prohibited:** `stale_reference` based solely on mtime, or `pass` asserting
  freshness.

### G-010 — Explicit version mismatch in a resolving reference

- **Kind / PRD:** positive; P0-R7, P0-R10, P0-R11; AC-2, AC-3.
- **Inputs:** the Skill metadata requires policy schema `3`; its reference
  resolves to a file declaring schema `2` and “not compatible with schema 3.”
- **Question:** Is the resolving reference fit for its declared purpose?
- **Expected:** `finding`; label `stale_reference`; severity `high`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** The target exists, so it is not invalid;
  the explicit incompatibility proves obsolescence for this consumer.
- **Acceptable uncertainty:** No claim is made about other consumers of schema
  2.
- **Prohibited:** `invalid_reference`, age-based rationale, or generic
  `configuration_risk` replacing the more precise label.

### G-011 — Reference escapes the disclosed workspace scope

- **Kind / PRD:** positive; P0-R1, P0-R7, P0-R29; AC-1, AC-3, AC-15.
- **Inputs:** an in-scope Skill declares `../../private/policy.md`; normalized
  resolution leaves the disclosed workspace, and the supported rule forbids
  escaping references. The outside file's contents are not read.
- **Question:** Is the declared reference valid in this scan scope?
- **Expected:** `finding`; label `invalid_reference`; severity `medium`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** Normalized target plus the declared scope
  boundary decides validity without inspecting sensitive content.
- **Acceptable uncertainty:** The outside target may exist.
- **Prohibited:** reading the file to “confirm,” reporting it merely missing, or
  claiming malicious intent.

### G-012 — Documented Skill-list truncation

- **Kind / PRD:** positive; P0-R4, P0-R9, P0-R10; AC-1–AC-3, AC-14.
- **Inputs:** the recorded platform/rule version has a documented maximum of 100
  entries in the relevant initial Skill list. The in-scope inventory contains
  112 eligible entries, and the observed generated list contains the first 100.
- **Question:** Is there a deterministic context/list-budget risk?
- **Expected:** `finding`; label `context_budget_risk`; severity `medium`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** Versioned limit, eligible count, and
  observed omission prove truncation.
- **Acceptable uncertainty:** The example does not claim which omitted Skill a
  future prompt would need.
- **Prohibited:** guaranteed runtime failure, byte-to-token estimates, or
  hiding the 12 omitted sources.

### G-013 — Large descriptions with unknown allocation

- **Kind / PRD:** boundary; P0-R9, P0-R11–R14, P1-R6; AC-6.
- **Inputs:** several Skill descriptions are verbose, but the fixture has no
  current documented budget, tokenizer basis, generated-list measurement, or
  observed truncation.
- **Question:** Do the descriptions create a context-budget finding?
- **Expected:** `insufficient_evidence`; no `context_budget_risk` finding;
  confidence `high` in abstention; static decision unavailable.
- **Rationale / decisive evidence:** Visual length alone cannot establish the
  relevant loaded size or budget consequence.
- **Acceptable uncertainty:** The report may record measured bytes as inventory
  facts, clearly separated from diagnosis.
- **Prohibited:** high-confidence risk, guessed token count, or `pass` asserting
  no risk.

### G-014 — Unsupported required metadata value

- **Kind / PRD:** positive; P0-R8–R10; AC-2, AC-3.
- **Inputs:** a required field `mode` is set to `sometimes`; the applicable
  versioned schema permits only `always` or `on_request`, and invalid values
  cause the declaration to be ignored.
- **Question:** Is the configuration valid and behaviorally relevant?
- **Expected:** `finding`; label `configuration_risk`; severity `medium`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** The exact value violates the applicable
  schema, with a documented discovery effect.
- **Acceptable uncertainty:** Whether a user prompt would have needed the
  ignored declaration is a runtime question.
- **Prohibited:** treating the unknown value as forward-compatible without
  evidence, or calling this an `invalid_reference`.

### G-015 — Semantic checks disabled

- **Kind / PRD:** boundary; P0-R13, P0-R26, P0-R31; AC-14, AC-17.
- **Inputs:** semantic mode is explicitly disabled. Two Skill descriptions are
  inventoried; deterministic identity and reference checks complete, but
  semantic trigger comparison is not attempted.
- **Question:** Did the semantic-overlap check find no issue?
- **Expected:** `not_run` for semantic overlap; no semantic labels, severity, or
  substantive confidence; statically decidable `yes` as a run fact.
- **Rationale / decisive evidence:** Run configuration proves the check was
  skipped, while deterministic results remain usable.
- **Acceptable uncertainty:** The Skills may or may not overlap.
- **Prohibited:** semantic `pass`, `insufficient_evidence`, or suppressing the
  deterministic results.

### G-016 — Broad triggers, undisclosed bodies

- **Kind / PRD:** boundary; P0-R12, P0-R28–R29, P1-R1–R3, P1-R6; AC-6, AC-15.
- **Inputs:** both descriptions say “use for code review,” but their bodies are
  outside the user-approved semantic disclosure/inspection scope. No narrower
  exclusions or behavior can be established.
- **Question:** Are the Skills redundant or conflicting?
- **Expected:** `insufficient_evidence` for the redundancy/conflict question;
  a separate overlap subquestion may return a medium-confidence
  `scope_overlap` candidate if the descriptions themselves are approved and a
  witness is recorded; no redundancy/conflict label; severity unknown.
- **Rationale / decisive evidence:** Descriptions can support possible overlap,
  but the uninspected claims are decisive for behavioral classification.
- **Acceptable uncertainty:** A narrower follow-up inspection may resolve it;
  the analysis must not expand disclosure silently.
- **Prohibited:** forced `behavioral_redundancy`, conflict, pass, or reading the
  bodies without approval.

### G-017 — Testable routing ambiguity without observed failure

- **Kind / PRD:** positive candidate; P1-R1, P1-R6, P2 runtime boundary; AC-5,
  AC-6.
- **Inputs:** two Skills explicitly claim the exact same witness requests and
  both say they are the primary handler, but their actions are compatible and
  materially distinct. No documented deterministic routing tie-breaker or run
  trace exists.
- **Question:** Will routing choose an unintended handler?
- **Expected:** `candidate`; label `scope_overlap`; qualifier
  `runtime_validation_needed`; severity `medium` potential impact; confidence
  `medium`; statically decidable `no` for selection outcome.
- **Rationale / decisive evidence:** Identical trigger witnesses support a
  falsifiable selection-risk hypothesis, not a proven conflict or failure.
- **Acceptable uncertainty:** Controlled runs could show stable correct routing
  and close the candidate.
- **Prohibited:** `finding` that misrouting occurred, `semantic_conflict`, or
  `insufficient_evidence` without stating the available testable hypothesis.

### G-018 — One pair, different labels by dimension

- **Kind / PRD:** boundary; P0-R15, P1-R2, P1-R5; AC-3, AC-7.
- **Inputs:** two review Skills share the same trigger. Both require a risk
  summary (redundant output dimension). One requires asking before editing,
  while the other requires editing without questions (conflicting action/
  question-policy dimensions).
- **Question:** How should one user-visible interaction be represented?
- **Expected:** one grouped `finding` with region/dimension-qualified labels:
  `scope_overlap`, `behavioral_redundancy` for risk summary, and
  `semantic_conflict` for edit/question policy; severity `high`; confidence
  `high`; statically decidable `yes` for textual relations.
- **Rationale / decisive evidence:** The evidence describes one routing
  interaction, but mutually exclusive semantic labels apply to different
  dimensions and therefore do not violate the multi-label rule.
- **Acceptable uncertainty:** Runtime selection remains unclaimed.
- **Prohibited:** duplicate user findings for each repeated line, calling the
  entire pair only redundant, or applying conflict and redundancy to the same
  exact claim/dimension.

### G-019 — Disjoint directory scopes despite identical text

- **Kind / PRD:** negative; P0-R3, P1-R1, P1-R3; AC-5–AC-7.
- **Inputs:** `frontend/AGENTS.md` requires browser tests for changes under
  `frontend/`; `backend/AGENTS.md` contains identical wording but applies only
  under `backend/`. The selected change is `frontend/button.ts`.
- **Question:** Do the two sources overlap or duplicate active behavior here?
- **Expected:** `pass`; label `no_material_relation`; severity `info`;
  confidence `high`; observed + derived evidence; statically decidable `yes`.
- **Rationale / decisive evidence:** Directory scopes are disjoint for the
  selected file; repeated wording alone is not active redundancy.
- **Acceptable uncertainty:** A cross-directory change would be a different
  diagnostic unit.
- **Prohibited:** `scope_overlap` or `behavioral_redundancy` from text
  similarity alone.

### G-020 — Read failure after a check starts

- **Kind / PRD:** boundary; P0-R4, P0-R13; AC-1, AC-3.
- **Inputs:** an applicable source was inventoried, the validity check began,
  and the file became unreadable before required metadata could be inspected.
- **Question:** Did the validity check run to a diagnostic conclusion?
- **Expected:** `error`, not a substantive taxonomy label; affected source and
  incomplete check named; severity not assigned; retry/permission evidence
  recorded.
- **Rationale / decisive evidence:** This is execution failure, distinct from a
  deliberately skipped check and from a successful check lacking semantic
  evidence.
- **Acceptable uncertainty:** If metadata had already proved an invalid
  reference before the read failure, that separable finding may remain.
- **Prohibited:** `not_run`, `pass`, or invented `invalid_reference`.

## 8. PRD and acceptance-criteria traceability

| Taxonomy/example area | PRD requirements | Acceptance criteria | Representative examples |
| --- | --- | --- | --- |
| Scope, inventory, precedence | P0-R1–R5, P0-R9 | AC-1, AC-3, AC-4 | G-006, G-007, G-011, G-019, G-020 |
| Deterministic duplicates, references, metadata, budget | P0-R6–R10 | AC-2, AC-3, AC-14 | G-004, G-008, G-010–G-014 |
| Evidence typing, uncertainty, deduplication | P0-R11–R15 | AC-3, AC-6 | G-001, G-007, G-009, G-013, G-016, G-018, G-020 |
| Offline and degraded semantic mode | P0-R26, P0-R31 | AC-14, AC-17 | G-012, G-015 |
| Disclosure and minimized inspection | P0-R28–R29 | AC-15, AC-16 | G-011, G-016 |
| Trigger overlap and distinct regions | P1-R1 | AC-5–AC-7 | G-003, G-005, G-016, G-017, G-019 |
| Contradictory actions and constraints | P1-R2 | AC-5, AC-7 | G-001, G-002, G-006, G-018 |
| Conflict/redundancy/complementarity/override distinction | P1-R3 | AC-7 | G-001–G-007, G-018–G-019 |
| Positive, negative, boundary examples | P1-R4 | AC-2, AC-5, AC-6 | G-001–G-020 |
| Multi-file grouping | P1-R5 | AC-3, AC-4 | G-004, G-018 |
| Confidence and abstention | P1-R6 | AC-5, AC-6 | G-003, G-007, G-009, G-013, G-016–G-017 |
| Stable/versioned future outputs | P0-R5, P1-R7–R10 | AC-3, AC-4 | Schema fields and all stable G-IDs |

This Stage 02 set supports the product targets in AC-2 and AC-5 but does not
claim that twenty specification examples are a statistically sufficient
evaluation corpus. Stage 04 must materialize fixtures, expand coverage, define
scoring units and thresholds, and prevent train/evaluation leakage.

## 9. Internal consistency and coverage review

The 2026-08-16 review applied these checks:

- **Class coverage:** every required relationship, defect, state, and qualifier
  has a full class contract and at least one representative case.
- **Polarity coverage:** the set includes 8 positive/problem cases, 4 negative
  cases, and 8 boundary cases. Candidates and abstentions are intentional, not
  counted as false negatives.
- **Evidence coverage:** observed, derived, inferred, and explicitly absent
  runtime evidence all appear; no example treats model or runtime behavior as
  deterministic proof.
- **Boundary coverage:** overlap versus conflict, overlap versus complementarity,
  invalid versus stale reference, precedence versus active conflict,
  insufficient evidence versus not run versus error, and static hypothesis
  versus runtime outcome each have a discriminating case.
- **Multi-label consistency:** G-018 qualifies labels by dimension; G-006 does
  not call a resolved override an active conflict; G-015 applies `not_run` only
  to the skipped family.
- **PRD traceability:** all Stage 02-relevant P0/P1 requirements and AC-1–AC-7,
  AC-14–AC-17 have an explicit mapping. Repair AC-8–AC-13 are intentionally
  unchanged and out of this stage's focus.
- **Scope discipline:** the document contains no implementation architecture,
  technology selection, provider choice, or unsupported runtime commitment.

### 9.1 Review assumptions to carry forward

1. Exact Codex discovery, precedence, and context-budget behavior is treated as
   versioned evidence, not frozen permanently by this taxonomy.
2. A future machine-readable representation must preserve the three axes and
   dimension/region qualifiers; its physical schema is not selected here.
3. Golden examples are normative specifications until Stage 04 materializes
   and independently reviews executable fixtures.
4. Confidence thresholds and blocking policy remain later quality-gate work;
   this document defines meanings, not release thresholds beyond the PRD.
