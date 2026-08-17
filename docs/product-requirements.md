# Agent Doctor Product Requirements Document

| Field | Value |
| --- | --- |
| Status | Review draft |
| Version | 0.1 |
| Date | 2026-08-16 |
| Canonical language | English |
| Companion review copy | [中文](product-requirements.zh-CN.md) |
| Product stage | Product definition only |

## 1. Executive summary

Agent Doctor is a local, Codex-first diagnostic product for people who use or
author multiple agent Skills and instruction files. It helps users understand
when individually reasonable configurations become ambiguous, redundant,
contradictory, unexpectedly broad, or wasteful when used together.

The product is read-only by default. It may apply a proposed repair only after
the user has granted bounded authorization in advance or explicitly confirmed
the exact change set before it is written. Every supported write must be
reviewable, attributable, verifiable, and reversible.

The MVP prioritizes precise, explainable findings over maximum coverage. It may
return `insufficient evidence` rather than manufacture a confident diagnosis.

## 2. Problem and opportunity

As users install more Skills and layer global, repository, and directory-level
instructions, configuration quality stops being a property of each file in
isolation. Safe components may still interact badly:

- two Skills may compete for the same request;
- two instructions may require incompatible actions or output formats;
- a Skill may claim a broader trigger surface than its actual purpose;
- an override may silently change which instruction governs a directory;
- stale references, duplicate content, or oversized descriptions may create
  noise and consume context;
- users may not know whether a suspected conflict is proven by static evidence
  or merely inferred from likely runtime behavior.

Existing security scanners primarily ask whether a Skill is malicious or
unsafe. Agent Doctor instead asks whether a set of otherwise legitimate agent
configurations works coherently, and whether a proposed remedy is justified by
traceable evidence.

## 3. Product vision

Give every advanced agent user a trustworthy local diagnostic that can answer:

1. What agent configuration is active here?
2. Which parts overlap, conflict, override, duplicate, or fail?
3. What evidence supports each conclusion?
4. What should I change, and what is the likely consequence?
5. If I authorize a repair, can I review and safely undo it?

The broader `Agent Doctor` name is retained so the product can eventually
diagnose additional agent systems. The MVP remains deliberately Codex-first.

## 4. Goals

### 4.1 MVP goals

- Inventory supported Codex Skills, `AGENTS.md` instruction chains, and related
  configuration inputs relevant to the selected workspace.
- Detect high-confidence deterministic problems without requiring a cloud
  model.
- Detect and explain semantic overlap and conflicts when the user enables a
  model-backed analysis mode.
- Separate facts, inferences, and unknowns in every report.
- Produce useful terminal, Markdown, JSON, and CI outcomes.
- Recommend bounded repairs without modifying files by default.
- Apply only an exact, reviewable change set under valid user authorization.
- Provide reliable rollback for every change type the product claims to
  support.
- Operate with data minimization and explicit disclosure of any content sent to
  a model provider.

### 4.2 Longer-term goals

- Incorporate runtime evidence to validate or refute static hypotheses.
- Support team governance and policy baselines.
- Add adapters for other agent ecosystems after the Codex model is proven.

## 5. Non-goals

The MVP will not:

- guarantee which Skill a model will choose for every future prompt;
- claim runtime causality when only static evidence is available;
- replace malware, prompt-injection, dependency, or supply-chain scanners;
- automatically repair files without prior bounded authorization or
  confirmation of the exact change set;
- provide an unrestricted autonomous maintenance mode;
- support Claude Code, Gemini CLI, or every agent framework;
- provide a hosted SaaS dashboard, organization administration console, or
  billing system;
- offer a desktop GUI or IDE-first experience;
- optimize general prompts or rewrite arbitrary project documentation;
- define the final implementation architecture in this PRD.

## 6. Target users

### 6.1 Primary: advanced individual agent user

A developer or knowledge worker who has installed many Skills, uses global and
project-specific instructions, and needs to understand why their setup feels
unpredictable or bloated.

Needs:

- a fast, local explanation of the active configuration;
- confidence that diagnosis will not alter the setup;
- evidence precise enough to make a manual repair;
- an optional safe path to apply and undo an approved repair.

### 6.2 Primary: Skill author or maintainer

An author who wants to know whether a Skill is too broad, duplicates an
existing Skill, conflicts with common instructions, or creates ambiguous
trigger behavior.

Needs:

- reproducible findings suitable for issue reports and CI;
- positive, negative, and boundary examples;
- machine-readable results and stable issue identifiers;
- advice that distinguishes a Skill defect from an installation-specific
  interaction.

### 6.3 Secondary: team platform engineer

A maintainer responsible for a shared agent setup. This persona influences
reporting and CI requirements but does not drive MVP administration features.

## 7. Core user journeys

### Journey A: diagnose an unpredictable local setup

1. The user selects a workspace or supported configuration scope.
2. Agent Doctor explains what it will inspect and confirms read-only mode.
3. It inventories the active and relevant configuration sources.
4. It reports deterministic defects, semantic conflict candidates, evidence,
   severity, confidence, and suggested next actions.
5. The user resolves findings manually or requests a repair proposal.

### Journey B: review and apply a suggested repair

1. The user selects one or more findings.
2. Agent Doctor produces an exact proposed change set, expected effects, risks,
   validation plan, and rollback availability.
3. The product verifies either:
   - an existing, bounded authorization covers these files and operations; or
   - the user explicitly confirms this exact change set before writing.
4. The product applies only the approved changes and verifies the resulting
   state.
5. It records what changed and presents a rollback action.
6. On rollback, it restores the prior state without overwriting unrelated
   concurrent changes. If safe rollback is no longer possible, it stops and
   explains the conflict.

### Journey C: validate a Skill before publishing

1. A Skill author runs Agent Doctor against the Skill and a representative set
   of installed instructions.
2. The report identifies overly broad triggers, missing exclusions, duplicates,
   contradictions, invalid references, and unresolved ambiguity.
3. CI receives a stable machine-readable result and exit status.
4. The author uses the evidence and later golden examples to revise the Skill.

### Journey D: run without sharing content with a model

1. The user disables semantic coverage, declines the exact disclosure
   manifest, or has no available model provider.
2. Agent Doctor completes all deterministic checks locally.
3. The report clearly labels semantic checks as not run, rather than passed.

## 8. Product principles

1. **Read-only by default.** Analysis must never imply permission to write.
2. **Authorization is bounded.** Permission names the targets, operation class,
   and applicable session or duration; it is not a permanent blanket grant.
3. **Preview before write.** An exact change set is shown before every write,
   including writes covered by pre-authorization.
4. **Rollback is part of the change.** A write is unsupported unless its prior
   state can be captured and a safe rollback path can be offered.
5. **Evidence before confidence.** Findings cite the source and distinguish
   observed facts from semantic inference.
6. **Precision before coverage.** It is acceptable to abstain.
7. **Local and minimal by default.** Deterministic analysis is offline; external
   model use is optional and disclosed.
8. **No silent scope expansion.** Discovery, model submission, modification,
   and rollback each stay inside the scope presented to the user.

## 9. Scope model

### 9.1 MVP inputs

- Codex Skill manifests and `SKILL.md` content;
- directly referenced Skill resources needed to validate a finding;
- applicable global, repository, and nested `AGENTS.md` or override files;
- supported configuration values that influence discovery, scope, or context;
- user-selected workspace and analysis settings.

Scripts and referenced files are treated as sensitive by default. Their
existence and metadata may be inspected for deterministic validation, but their
contents must not be sent to a model unless the user has been shown and has
approved the disclosure scope.

### 9.2 MVP outputs

- human-readable terminal summary;
- durable Markdown report;
- versioned JSON result;
- CI-compatible exit outcome;
- optional repair proposal;
- optional approved change record and rollback record.

### 9.3 Finding states

Every check must end in one of these states:

- `pass`: the defined condition was checked and no issue was found;
- `finding`: sufficient evidence supports a problem;
- `candidate`: evidence suggests a possible problem but needs judgment or
  runtime validation;
- `insufficient_evidence`: the product cannot responsibly decide;
- `not_run`: the check was unavailable, disabled, or outside scope;
- `error`: the check could not complete.

`not_run` and `insufficient_evidence` must never be presented as `pass`.

## 10. Requirements and priorities

Priority meanings:

- **P0:** required for the MVP to be trustworthy and releasable;
- **P1:** required for a useful public v0.1, but may follow the first vertical
  slice;
- **P2:** explicitly deferred until the MVP foundation is validated.

### 10.1 P0 — scope and inventory

- P0-R1: Show the analysis scope before scanning.
- P0-R2: Identify supported Skill and instruction sources relevant to the
  selected workspace.
- P0-R3: Explain source precedence and effective scope where deterministically
  knowable.
- P0-R4: Report ignored, shadowed, truncated, missing, or unreadable sources
  without silently omitting them.
- P0-R5: Record product version, rule-set version, time, scope, and enabled
  analysis modes in durable outputs.

### 10.2 P0 — deterministic diagnostics

- P0-R6: Detect duplicate identifiers and structurally duplicate installations.
- P0-R7: Detect broken or escaping references within the supported scope.
- P0-R8: Detect malformed required metadata and unsupported declarations.
- P0-R9: Detect deterministically knowable precedence, override, and context
  budget risks.
- P0-R10: Provide source location, rule identifier, severity, and remediation
  guidance for every deterministic finding.

### 10.3 P0 — evidence and uncertainty

- P0-R11: Label every conclusion as observed, derived, or inferred.
- P0-R12: Include sufficient source excerpts or locations for independent
  review without exposing unrelated secrets.
- P0-R13: Use explicit candidate, insufficient-evidence, not-run, and error
  states.
- P0-R14: Never present model output alone as deterministic proof.
- P0-R15: Deduplicate substantially identical findings and explain relationships
  among related findings.

### 10.4 P0 — safe repair and rollback

- P0-R16: Start every run in read-only mode unless a bounded authorization is
  explicitly supplied.
- P0-R17: A repair proposal must show exact targets, proposed differences,
  rationale, expected effect, risk, verification, and rollback availability.
- P0-R18: Writing requires either a valid bounded pre-authorization or explicit
  confirmation of the exact proposal before it is applied.
- P0-R19: Pre-authorization must be limited by target scope, allowed operation
  class, and session or expiry boundary, and must be revocable.
- P0-R20: Even under pre-authorization, the product must present the change set
  before writing and must not expand it silently.
- P0-R21: Capture the relevant prior state before writing and verify that the
  target has not changed since proposal generation.
- P0-R22: Apply only the approved change set; partial or conflicting application
  must stop with an explicit state report.
- P0-R23: Verify post-change conditions and preserve an attributable change
  record.
- P0-R24: Offer rollback for every supported write and refuse rollback rather
  than overwrite unrelated concurrent user changes.
- P0-R25: An analysis request, model-use consent, or permission to inspect is
  never equivalent to write permission.

### 10.5 P0 — privacy and model use

- P0-R26: Complete deterministic analysis without a model or network access.
- P0-R27: Enable semantic coverage and bounded question planning by default.
  An explicit comprehensive semantic-diagnosis operation authorizes only the
  immediately generated one-run disclosure manifest; every provider call must
  still be mechanically bound to its exact digest. Retain standalone
  prepare/invoke as an inspect-and-confirm workflow. Support explicit
  disablement, exact inclusion/exclusion scope, and a user-provided credential
  or provider configuration.
- P0-R28: Before a standalone model invocation, disclose the provider and exact
  file/content scope eligible for submission. A one-shot run must record the
  same manifest, exclusions, provider/model/effort, purpose, and digest in its
  local audit artifacts before starting any provider process; it grants no
  persistent or background authorization.
- P0-R29: Exclude secrets, executable scripts, and unrelated full referenced
  files by default.
- P0-R30: Record which checks used a model without recording secrets or raw
  credentials.
- P0-R31: If semantic coverage is disabled or the provider is unavailable,
  mark it `not_run`. A deterministic `scan` with semantic coverage enabled but
  no provider panel reports the panel as pending rather than disabled or
  passed; an explicit comprehensive diagnosis proceeds through the bounded
  one-shot semantic workflow unless the user disables, narrows, or excludes it.
  If exact scope resolution leaves fewer than two Skills, record a distinct
  `semantic_relationship_scope_not_applicable` applicability pass with zero
  provider calls; do not represent relationship analysis itself as completed
  and do not widen the scope.
- P0-R32: Run two blind analysts concurrently in isolated ephemeral contexts,
  then a third fresh-context judge after both validate. A resolved analyst
  disagreement must remain visible and may be at most a candidate; only local
  deterministic rules may assign product state, severity, confidence,
  provenance, grouping, or repair compatibility.

### 10.6 P1 — semantic diagnosis

- P1-R1: Identify overlapping Skill trigger surfaces and explain the shared and
  distinct regions.
- P1-R2: Identify contradictory required actions, forbidden actions, question
  policies, output constraints, and applicability boundaries.
- P1-R3: Distinguish conflict, redundancy, complementarity, override, and
  uncertainty rather than treating similarity as conflict.
- P1-R4: Suggest positive, negative, and boundary examples for later evaluation.
- P1-R5: Group multi-file evidence into a single interaction finding when that
  better represents the user problem.
- P1-R6: Assign calibrated confidence and provide a reason for abstention.

### 10.7 P1 — reporting and CI

- P1-R7: Produce terminal, Markdown, and versioned JSON outputs from the same
  result set.
- P1-R8: Provide documented CI outcomes that distinguish execution failure from
  policy threshold failure.
- P1-R9: Support severity and confidence thresholds without hiding lower-level
  findings from durable reports.
- P1-R10: Use stable finding and rule identifiers suitable for baselines and
  issue tracking.
- P1-R11: Human reports rank findings and candidates by assigned or potential
  severity, show representative cited source excerpts with exact locations,
  distinguish deterministic findings from model-inferred findings and
  unconfirmed candidates, retain counterexamples, and count any items or
  excerpts omitted from a bounded terminal view. Unasked semantic questions
  are coverage gaps, not risks.

### 10.8 P2 — deferred capabilities

- Runtime trace collection and causal validation;
- automated regression generation from real failed sessions;
- team policy packs and centralized administration;
- adapters for non-Codex agent ecosystems;
- desktop or IDE-native interfaces;
- unattended recurring repair;
- hosted collaboration and analytics.

## 11. Severity and confidence

Severity describes likely user impact, not certainty:

- `critical`: could cause destructive or unauthorized behavior;
- `high`: likely to select the wrong workflow or violate a material constraint;
- `medium`: creates recurring ambiguity, duplication, or degraded results;
- `low`: creates maintainability, clarity, or context-efficiency debt;
- `info`: useful inventory or improvement opportunity.

Confidence is reported independently as high, medium, or low. Low-confidence
items should normally be candidates, not blocking findings.

The detailed conflict taxonomy and golden examples belong to the next project
stage and may refine these definitions without changing the product principles.

## 12. Product-level acceptance criteria

### 12.1 Scope and deterministic correctness

- AC-1: On the approved golden fixtures, the product inventories 100% of
  supported in-scope sources and reports every intentionally excluded source.
- AC-2: Deterministic P0 rules achieve at least 95% precision and 95% recall on
  the approved golden set, with no critical false negative.
- AC-3: 100% of findings include a rule identifier, severity, confidence or
  deterministic status, source location, evidence, and recommended next step.
- AC-4: The same underlying result produces semantically consistent terminal,
  Markdown, and JSON outputs.

### 12.2 Semantic usefulness

- AC-5: On the approved semantic golden set, blocking semantic findings achieve
  at least 90% precision; overall semantic findings achieve at least 85%
  precision and 75% recall.
- AC-6: Evaluators judge at least 80% of reported semantic findings actionable,
  and no intentionally ambiguous case is forced into `pass` or `finding`.
- AC-7: Conflict, redundancy, complementarity, override, and insufficient
  evidence are distinguishable in both human and JSON outputs.

These thresholds are product targets. Stage 02 defines the taxonomy and golden
examples; Stage 04 defines the formal measurement and release gates.

### 12.3 Authorization and change safety

- AC-8: In all negative authorization scenarios, zero files are modified.
- AC-9: Every proposed write displays the exact change set before application,
  including under pre-authorization.
- AC-10: A valid authorization cannot be reused outside its target, operation,
  session, or expiry scope.
- AC-11: For every supported repair type, rollback restores the exact captured
  prior state when no concurrent change exists.
- AC-12: If a target changes after proposal or application, Agent Doctor detects
  the conflict and does not overwrite unrelated changes during apply or
  rollback.
- AC-13: Applied, partially applied, rejected, failed, and rolled-back states are
  unambiguous and attributable in the change record.

### 12.4 Privacy and degraded modes

- AC-14: All deterministic P0 checks complete with network access unavailable.
- AC-15: No content is sent to a model unless semantic coverage is enabled,
  the eligible submission scope has been disclosed, and the user has affirmed
  that exact manifest digest.
- AC-16: Secret fixtures and unapproved script contents never appear in model
  requests, reports, or change records.
- AC-17: When model analysis is unavailable, deterministic results remain usable
  and semantic checks are labeled `not_run`.

## 13. Success measures

MVP success is demonstrated when:

- advanced users can identify at least one real configuration problem or gain
  justified confidence that a suspected problem lacks evidence;
- Skill authors can reproduce findings locally and in CI;
- users can explain why a blocking finding exists without trusting an opaque
  score;
- no pilot run writes without valid authorization;
- all supported pilot repairs can be reviewed and safely rolled back;
- at least 80% of pilot users rate the report as more useful than manually
  reviewing the same configuration files.

Adoption volume, paid conversion, and enterprise administration are not MVP
success criteria.

## 14. Risks and product responses

| Risk | Product response |
| --- | --- |
| Semantic false positives erode trust | Precision-first thresholds, candidates, abstention, and evidence |
| Static analysis is mistaken for runtime truth | Separate observed, inferred, and runtime-unverified claims |
| Repair capability expands perceived authority | Read-only default, bounded authorization, exact preview, and revocation |
| Rollback overwrites later user work | Prior-state capture plus concurrent-change detection and safe refusal |
| Model use leaks sensitive content | Explicit bounded semantic operation, exact one-run disclosure authorization, minimization, and default exclusions |
| Product duplicates security scanners | Keep coherence and interaction diagnosis as the explicit category boundary |
| Codex behavior evolves | Version findings, rules, inputs, and cited behavior assumptions |
| Early multi-platform scope dilutes quality | Prove the Codex-first taxonomy and evaluation set before adding adapters |

## 15. Dependencies and follow-on deliverables

This PRD intentionally leaves the following to separate stages:

1. **Conflict taxonomy and golden examples:** precise classes, boundary cases,
   adjudication rules, and labeled fixtures.
2. **Detailed design and architecture:** domain model, components, persistence,
   provider abstraction, authorization representation, and rollback mechanism.
3. **Test scenarios and quality gates:** complete scenario matrix, measurement
   protocol, threat cases, and release gating.
4. **MVP implementation:** code, packaging, CI integration, and release.

No architecture or implementation choice is approved merely because a product
requirement names an outcome.

## 16. Approved product decisions

| Decision | Approved direction |
| --- | --- |
| Primary users | Advanced individual users and Skill authors |
| Initial ecosystem | Codex-first |
| Default authority | Read-only |
| Optional writes | Bounded pre-authorization or exact pre-write confirmation |
| Rollback | Required for every supported write |
| Product form | Local CLI first |
| Deterministic mode | Offline |
| Semantic mode | Enabled for explicit comprehensive diagnosis through the signed-in Codex route; explicitly disable/narrow it; exact one-run disclosure and data minimization required |
| Judgment strategy | Precision and explainability before coverage; abstention allowed |
| Brand | Agent Doctor |
| Repository | Public, MIT |
| Documentation | English canonical PRD and complete Chinese review copy |

## 17. Source assumptions

This PRD relies on current official OpenAI documentation for the following
product assumptions:

- Skills package instructions, resources, and optional scripts; Codex initially
  sees Skill names and descriptions and applies a bounded context budget to the
  Skill list: <https://learn.chatgpt.com/docs/build-skills>.
- Codex discovers and layers global, project, and nested `AGENTS.md` guidance in
  a defined order: <https://learn.chatgpt.com/docs/agent-configuration/agents-md>.
- Hooks expose selected lifecycle and tool events that may support later runtime
  evidence: <https://learn.chatgpt.com/docs/hooks>.
- The Codex SDK can control local Codex agents programmatically and may support a
  later runtime validation layer: <https://learn.chatgpt.com/docs/codex-sdk>.

These are scope assumptions, not detailed design decisions. If documented
platform behavior changes, the relevant rules and acceptance fixtures must be
reviewed.
