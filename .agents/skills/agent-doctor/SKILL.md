---
name: agent-doctor
description: Run and explain safe local Agent Doctor diagnostics for a workspace or installed Codex Skill set. Use when a user asks to inventory Skills, inspect configuration conflicts or coverage gaps, run a consented semantic comparison, interpret a sealed Agent Doctor result, inspect the reviewed OpenAI model-routing policy, compare repository changes with the Stage 01–06 contracts, or plan an evidence-based manual follow-up. Do not use it to claim runtime causality, perform undisclosed semantic inspection, treat a model recommendation as qualification, or apply repairs.
---

# Agent Doctor

Use the local deterministic engine as the evidence source and Codex as the
orchestrator and explainer. Preserve the product's three diagnostic axes and
never upgrade static filesystem evidence into runtime selection or causality.

## Run the safe workflow

1. Locate the repository root containing `pyproject.toml`, `src/agent_doctor`,
   and `test-spec`.
2. Freeze the requested scope before scanning:
   - default to the workspace only;
   - add `--include-user` only when the user explicitly asks to inspect their
     user-level Skill set;
   - keep `--project-trust unknown` unless trust was independently established;
   - never add `--include-system` merely to broaden coverage.
3. Prefer the installed `agent-doctor` command. From a source checkout, use
   `PYTHONPATH=src python3 -m agent_doctor` when the package is not installed.
4. Use the default human-first terminal projection for interpretation. Use
   `--format debug` only when durable IDs and compact technical state are the
   primary need:

   ```sh
   PYTHONPATH=src python3 -m agent_doctor scan . --format terminal
   ```

   Add the approved scope flags without changing their meaning. Do not read a
   full JSON/Markdown evidence projection into model context unless a future
   manifest-specific semantic-disclosure workflow has explicitly authorized
   that content.
5. Confirm the summary explains what needs attention, the affected Skill
   locations, impact/confidence, per-Skill bounded health dimensions, unknowns,
   and manual next steps. Durable IDs remain in the technical-reference tail.
6. Explain what is established, what is only a candidate, and what remains
   unknown. Keep execution failure separate from CI policy failure.

## Interpret findings

- Treat `pass`, `finding`, `candidate`, `insufficient_evidence`, `not_run`, and
  `error` as check states, not substantive meanings.
- Report substantive labels and runtime-validation qualifiers independently.
- Cite case IDs, check IDs, source IDs, and evidence IDs that appear in the
  projection; do not invent missing lineage.
- Call locally observed Codex-home/plugin-cache Skills “observed artifacts,”
  not active Skills, unless independent runtime evidence exists.
- Describe `complete_with_gaps` as a usable partial result, not a clean bill of
  health.
- Keep repair advice proposal/manual-only. Never edit installed Skills as an
  implied continuation of diagnosis.

## Semantic boundary

The CLI exposes a consented Codex Desktop semantic exchange. It is a
developmental, unqualified evidence path: it can produce a sealed local result,
but it has not completed the Stage 04 measurement protocol and cannot support
accuracy, calibration, usefulness, or release-readiness claims.

Do not bypass the exchange by directly reading personal Skill bodies and
calling an informal model opinion an Agent Doctor finding.

For a request for a **comprehensive Skill health diagnosis**, do not stop after
the deterministic scan. Prepare the semantic panel for the approved Skill
scope, show the exact disclosure, and pause for digest-specific consent. If the
user declines or has not yet consented, report semantic relationships as not
completed; never silently downgrade that gap into a clean result.

1. Confirm the requested semantic scope. If a phrase is unrelated, irrational
   in context, or looks like a voice-transcription artifact, ask the user to
   confirm it before adding a source, capability, or feature.
2. Run semantic prepare with semantic mode enabled, the approved local scope,
   and every exact Skill source location. This step calls no model.
3. Show the user the exact manifest digest, provider, model, reasoning effort,
   purpose, selected locations, disclosed claim counts, exclusions,
   retention/cache statement, and qualification state. The manifest includes
   only minimized claim excerpts. Secret-bearing sources and script bodies are
   excluded.
4. Require a new affirmative reply bound to that exact digest. A general
   request to turn semantic mode on is not manifest-specific consent. If the
   source revision, model, effort, provider, purpose, or content changes,
   prepare a new manifest and request new consent.
5. Only after exact consent, run semantic invoke with the package and consent
   digest. It runs two isolated ephemeral signed-in Codex turns in empty
   temporary directories: a bounded analyst, then a fresh-context critic that
   reads the two sources in reversed order and actively attempts to refute each
   answer. Both ignore user/project rules, request tool/web/app disabling, and
   are rejected if tool activity is observed. No OpenAI API key is required.
6. Run semantic finalize against the same local scope, package, invocation, and
   exact consent digest. Render the resulting sealed graph in the requested
   terminal, Markdown, or JSON projection.
7. Treat both panel outputs only as cited inferred evidence. Local promotion
   requires the same frozen question/source/dimension identity, complete
   citations, critic corroboration, excluded counterexamples, and no missing
   evidence. Local rules retain final state, labels, independent diagnostic
   dimensions, severity, confidence, recommendation compatibility,
   applicability qualifiers, grouping, and sealing. Recommendations are
   proposal/manual-only and cannot authorize a write. Never turn static Skill
   text into runtime selection or causality.

## Model-routing boundary

Use the local resolver when the user asks which reviewed model route is
configured. It does not call OpenAI:

```sh
PYTHONPATH=src python3 -m agent_doctor model resolve \
  --capability semantic.reasoning_quality_first
```

Keep official recommendation, account availability, user policy, and Stage 04
qualification separate. `/v1/models` proves availability only. A user pin is
exact and must not be silently replaced.

Run `model check-official` only when the user asks to verify current official
documentation and make the network boundary explicit first. A drift report
creates a candidate review; it never promotes a model automatically. The
Codex Desktop semantics are available only through the disclosure, consent,
response-validation, and local-adjudication sequence above. They remain
unqualified until the Stage 04 measurement protocol is completed.

## Repository maintenance

For repository changes, run `make check` and `make package`. Do not weaken a
golden expectation to make an implementation pass, and do not claim accuracy,
usefulness, calibration, or release readiness from contract regressions alone.
