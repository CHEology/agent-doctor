---
name: agent-doctor
description: Run and explain safe local Agent Doctor diagnostics for a workspace or installed Codex Skill set. Use when a user asks to inventory Skills, inspect configuration conflicts or coverage gaps, interpret a sealed Agent Doctor result, compare repository changes with the Stage 01–05 contracts, or plan an evidence-based manual follow-up. Do not use it to claim runtime causality, perform undisclosed semantic inspection, or apply repairs.
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
4. Use the terminal projection for model-visible interpretation:

   ```sh
   PYTHONPATH=src python3 -m agent_doctor scan . --format terminal
   ```

   Add the approved scope flags without changing their meaning. Do not read a
   full JSON/Markdown evidence projection into model context unless a future
   manifest-specific semantic-disclosure workflow has explicitly authorized
   that content.
5. Confirm the summary names the result ID, sealing state, run outcome,
   inventory counts, case states, coverage gaps, and next actions.
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

The current product CLI does not expose the production semantic adapter. Do
not bypass that boundary by directly reading personal Skill bodies and calling
the resulting opinion an Agent Doctor finding. If the user requests behavioral
overlap or conflict analysis that needs model reasoning:

1. state that deterministic coverage is available now;
2. identify the missing semantic evidence precisely;
3. explain that Stage 06 must first produce an exact provider/model/purpose/
   content/exclusion/retention manifest and bind consent to its digest;
4. keep any informal model observation outside the sealed product result.

## Repository maintenance

For repository changes, run `make check` and `make package`. Do not weaken a
golden expectation to make an implementation pass, and do not claim accuracy,
usefulness, calibration, or release readiness from contract regressions alone.
