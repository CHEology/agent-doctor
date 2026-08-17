---
name: agent-doctor
description: Run and explain comprehensive local Agent Doctor diagnostics for a workspace or installed Codex Skill set, with bounded semantic analysis enabled by default, two blind parallel analysts, a fresh judge, and local final adjudication. Use when a user asks to inventory Skills, inspect configuration conflicts, trigger overlap, maintenance freshness, or coverage gaps, run a semantic comparison, interpret a sealed result, inspect model routing, compare Stage 01–06 contracts, or plan a manual follow-up. Do not use it to claim runtime causality, perform undisclosed semantic inspection, treat a model recommendation as qualification, or apply repairs.
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
   - never add `--include-system` merely to broaden coverage;
   - keep semantic coverage enabled unless the user explicitly requests a
     deterministic-only run;
   - for semantic preparation, omit `--source` to use the bounded auto scope,
     repeat `--source` to narrow it, and repeat `--exclude-source` to remove an
     exact source.
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
7. Keep content health, static applicability, runtime selection, and causality
   separate. Runtime selection may remain unobserved without turning every
   completed content-health card into `unknown`.

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
- For every displayed finding or candidate, show its judgment basis, assigned
  or potential severity, confidence, representative cited source sentences
  with exact locations, model-panel rationale when present, counterexample
  state, and durable case ID. In a bounded terminal answer, show the three
  highest-severity items and up to two representative lowest-severity items,
  then state exact omitted item/excerpt counts; use Markdown/JSON for complete
  detail.
- Treat planned or unanswered semantic questions as pending coverage, never as
  risks. Keep deterministic findings, locally adjudicated inferred findings,
  and unconfirmed candidates visibly distinct.
- Do not report a missing reference as `invalid_reference` when the declaring
  Skill explicitly defines that resource as optional or provides a single-file
  fallback contract. Explain the excluded suspicion or abstain if installation
  intent remains ambiguous.
- Interpret maintenance freshness only from an explicit version, rename,
  supersession, or compatibility contract. Never use file age alone. Report
  `insufficient_evidence` when a reference exists but no decisive freshness
  contract is in scope, and `not_applicable` when no reference contract exists.
- Keep repair advice proposal/manual-only. Never edit installed Skills as an
  implied continuation of diagnosis.

## Semantic boundary

The CLI exposes a manifest-bound Codex Desktop semantic exchange. It is a
developmental, unqualified evidence path: it can produce a sealed local result,
but it has not completed the Stage 04 measurement protocol and cannot support
accuracy, calibration, usefulness, or release-readiness claims.

Do not bypass the exchange by directly reading personal Skill bodies and
calling an informal model opinion an Agent Doctor finding.

Semantic analysis is on by default. For a request for a **comprehensive Skill
health diagnosis**, run the complete one-shot semantic workflow; do not stop
after deterministic preparation and do not ask for a redundant second reply.
The explicit diagnosis request authorizes only the immediately generated,
minimized one-run manifest. Honor an explicit request to disable semantic
analysis, narrow exact sources, or exclude exact sources. A plain `scan` is the
deterministic projection and must report its unexecuted semantic panel as
pending rather than a clean result.

1. Confirm the requested semantic scope. If a phrase is unrelated, irrational
   in context, or looks like a voice-transcription artifact, ask the user to
   confirm it before adding a source, capability, or feature.
2. For a comprehensive diagnosis, run `semantic run` with the approved local
   scope and a durable `--artifact-dir`. With no `--source`, use the bounded
   discovered non-inapplicable Skill scope. Use repeatable exact `--source` and
   `--exclude-source` selectors when the user narrows or excludes content. If
   fewer than two Skills remain, report cross-Skill semantic analysis as not
   applicable and confirm that no provider call started; never broaden scope
   silently just to create a pair.
3. The one-shot operation completes deterministic preparation, records the exact
   manifest/digest, launches analyst A and analyst B concurrently in separate
   empty ephemeral contexts, validates both, launches a third fresh-context
   judge, and locally finalizes the same sealed graph. Analyst B sees reversed
   source order; neither analyst sees the other. All three ignore user/project
   rules, request tool/web/app disabling, and are rejected if tool activity is
   observed. No OpenAI API key is required.
4. After completion, show the manifest digest, provider, model, reasoning effort,
   purpose, selected locations, disclosed claim counts, exclusions,
   retention/cache statement, qualification state, and artifact locations. The
   manifest includes only minimized claim excerpts, with trigger, delegation,
   and negative-routing boundaries prioritized before generic prose.
   Secret-bearing sources and script bodies are excluded.
5. If the user specifically asks to inspect disclosure before any provider call,
   use `semantic prepare`, show the package, then require exact-digest
   confirmation before `semantic invoke` and `semantic finalize`. Source,
   provider, model, effort, purpose, adapter, prompt, or content changes require
   a new package and digest.
6. Treat all three panel outputs only as cited inferred evidence. Local promotion
   requires the same frozen question/source/dimension identity, complete
   citations, analyst consensus, judge corroboration, excluded counterexamples,
   and no missing evidence. A judge-resolved analyst disagreement remains
   visible and can be at most a candidate. Local rules retain final state,
   labels, independent diagnostic
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
Codex Desktop semantics are available only through the disclosure, exact
manifest authorization, response-validation, and local-adjudication sequence
above. They remain
unqualified until the Stage 04 measurement protocol is completed.

## Repository maintenance

For repository changes, run `make check` and `make package`. Do not weaken a
golden expectation to make an implementation pass, and do not claim accuracy,
usefulness, calibration, or release readiness from contract regressions alone.
