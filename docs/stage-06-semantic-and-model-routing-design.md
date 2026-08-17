# Stage 06 — Semantic diagnosis and OpenAI model routing design

| Field | Value |
| --- | --- |
| Status | Local developmental provider path implemented; qualification pending |
| Design version | 0.5 |
| Date | 2026-08-17 |
| Canonical language | English |
| Companion review copy | [中文](stage-06-semantic-and-model-routing-design.zh-CN.md) |
| Governing contracts | [Stage 01](product-requirements.md), [Stage 02](conflict-taxonomy-and-golden-examples.md), [Stage 03](detailed-design-and-architecture.md), [Stage 04](test-scenarios-and-quality-gates.md) |

## 1. Outcome and current boundary

This design makes model choice capability-based, attributable, configurable,
and updateable without hard-coding “the numerically newest model wins.” It also
implements the local developmental semantic path in reviewable vertical slices.

The repository now implements the safe routing foundation:

- a reviewed OpenAI model-capability profile with official-source digests;
- an offline resolver for `auto` and exact user-pinned selection;
- separate account-availability, documentation-recommendation, and product-
  qualification states;
- current defaults for quality-first semantic reasoning;
- a read-only official-documentation drift checker;
- eleven executable model-routing scenarios;
- a weekly GitHub Actions profile watch; and
- user-overridable model and effort for the advisory Codex PR review;
- a deterministic semantic disclosure broker with secret/script exclusions;
- exact manifest-digest authorization and invalidation;
- an ephemeral signed-in Codex Desktop adapter that rejects observed tool use;
- a deterministic boundary-aware candidate-retrieval plan that preserves
  trigger, delegation, and negative-routing evidence before generic prose,
  prioritizes relevant pair/dimension questions, balances sources on equal
  scores, records that retrieval is selection-only, and discloses explicit
  truncation;
- two blind analysts in parallel, followed by a third fresh-context judge;
- closed cited-response and bounded recommendation contracts;
- local semantic adjudication into the same sealed result graph.

Semantic coverage is enabled by default and may be disabled or narrowed. An
explicit comprehensive semantic-diagnosis operation runs the bounded provider
panel by default and authorizes only its immediately generated one-run manifest;
ordinary deterministic `scan` never starts a provider. Standalone invocation
retains exact digest confirmation. No provider/model/adapter/prompt
identity has completed the Stage 04 qualification protocol, so a successful
run is not an accuracy, calibration, usefulness, or release-readiness claim.
The path uses the signed-in Codex Desktop account and does not require an
OpenAI API key; it does not prove availability to a separate API project.

## 2. Four facts that must never be collapsed

Model routing uses four independent facts:

| Fact | Source | What it proves | What it does not prove |
| --- | --- | --- | --- |
| Official recommendation | Reviewed OpenAI documentation profile | OpenAI currently documents a model for a named workload | Availability to this API project, Agent Doctor accuracy, cost fitness, or future behavior |
| Account availability | Authenticated `GET /v1/models` snapshot | An exact model ID is visible to the API project at that time | Which model is strongest, endpoint access, quota, or qualification |
| Product qualification | Stage 04 holdout and absolute gates | One provider/model/adapter/prompt contract met the declared evidence protocol | Another model, later model behavior, or a changed prompt/profile also qualifies |
| User policy | CLI/config/GitHub variable | The user requested `auto`, a capability tier, or an exact pin | That the choice is available, compatible, or qualified |

The resolver intersects these facts. It never sorts model names, treats a
creation timestamp as quality, or interprets the first `/v1/models` item as a
recommendation.

## 3. Dynamic selection lifecycle

“Dynamic” means a controlled update loop, not unreviewed runtime scraping:

```text
official Markdown changes
        |
        v
source-drift report --------> execution failure if sources cannot be checked
        |
        v
candidate profile diff
        |
        +--> source/capability review
        +--> routing contract tests
        +--> semantic holdout qualification when used for product findings
        |
        v
reviewed profile promotion by pull request
        |
        v
runtime resolver + account availability + user policy
```

The weekly `OpenAI model profile watch` workflow fetches only allowlisted
official Markdown URLs, checks content digests and constrained machine-readable
fields, and stores a drift report. Exit `2` means a valid drift report requires
policy review; exit `3` means the source check failed and no recommendation is
changed. The watcher has read-only repository permissions and no API key.

A detected model is only a **candidate**. Automatic promotion is forbidden
because documentation prose can change, a new model can be unavailable to the
account, and a product-semantic default must be requalified. A reviewed pull
request is the sole promotion path. This makes the system follow official
documentation while preserving Stage 03 profile and Stage 04 measurement
contracts.

### 3.1 Freshness and safe refusal

The bundled profile has `captured_at`, `review_after`, source URLs, source
digests, assertions, and a review record. After `review_after`, automatic
resolution refuses with `profile_stale`. Unknown, candidate, stale, or
incompatible profiles cannot support an automatic choice.

An exact user pin is not a bypass. The model must still be reviewed for the
requested capability, support the requested effort, and—before invocation—be
visible to the account. There is no implicit fallback. A future fallback must
name an equivalent capability, be explicitly enabled, and be recorded in the
selection digest.

## 4. Configuration contract

The default strategy is `auto`; the model ID is profile data rather than an
eternal code constant. For the reviewed 2026-08-17 profile:

| Capability | Current documented default | Effort | Current use |
| --- | --- | --- | --- |
| `codex.advisory_review` | `gpt-5.6-sol` | `max` | Optional read-only PR review; not product evidence |
| `semantic.reasoning_quality_first` | `gpt-5.6-sol` | `max` | Consented developmental Codex Desktop adapter; not qualified |
| `semantic.reasoning_balanced` | `gpt-5.6-terra` | `medium` | Explicit cost/quality tier; never silent fallback |
| `semantic.reasoning_high_volume` | `gpt-5.6-luna` | `medium` | Explicit high-volume tier; never silent fallback |

Current CLI examples:

```sh
# Resolve the reviewed default without calling OpenAI.
agent-doctor model resolve \
  --capability semantic.reasoning_quality_first \
  --as-of 2026-08-17

# Exact user pin and effort; still no provider call.
agent-doctor model resolve \
  --capability semantic.reasoning_balanced \
  --strategy pinned \
  --model gpt-5.6-terra \
  --reasoning-effort high \
  --available-model gpt-5.6-terra \
  --as-of 2026-08-17

# Require the product-semantic qualification gate. This currently reports a
# blocker because qualification has not been performed.
agent-doctor model resolve \
  --capability semantic.reasoning_quality_first \
  --available-model gpt-5.6-sol \
  --require-qualified --require-ready \
  --as-of 2026-08-17
```

The persistent configuration precedence for the production adapter is:

1. explicit CLI exact pin and effort;
2. trusted project Agent Doctor configuration;
3. user Agent Doctor configuration;
4. the current reviewed profile default.

Project configuration is ignored unless project trust is independently known.
Each resolved field records its source. Persistent Agent Doctor TOML loading is
not implemented; current semantic user control is explicit CLI selection and
an exact disclosure digest. Untrusted repository text cannot grant authorization
or trigger provider use.

The advisory workflow recognizes:

- `CODEX_REVIEW_MODEL`, defaulting to the reviewed profile model; and
- `CODEX_REVIEW_EFFORT`, defaulting to the reviewed profile effort.

Changing either is explicit user policy. Tests require workflow defaults and
the bundled profile to remain equal.

## 5. Selection artifact and invalidation

Every resolution emits a stable JSON decision containing:

- capability and `auto`/`pinned` strategy;
- exact model and reasoning effort;
- selection source;
- profile ID/version/capture/review dates;
- official source references;
- account-availability state and a digest of the supplied availability set;
- qualification state, attributable measurement-record reference, and whether
  qualification is required;
- blockers, invocation readiness, and whether a fallback occurred; and
- a decision ID and selection digest.

The selection digest is part of the disclosure-manifest digest,
semantic request metadata, cache key, reproducibility metadata, and provider
qualification identity. A model, effort, profile, capability, availability,
adapter, prompt contract, taxonomy, input, or policy change invalidates the
corresponding authorization/cache/qualification identity as required by Stage 03–04.

## 6. Production semantic pipeline design

The semantic pipeline extends the existing deterministic graph; it does not
replace it.

### 6.1 Ordered flow

1. Complete frozen scope, inventory, parsing, reference/configuration/
   precedence/applicability resolution, and all independent deterministic
   checks.
2. Retrieve candidate pairs by versioned lexical overlap and modality contrast,
   then build one semantic question for one claim set, region, and dimension
   where semantic evidence can add value. Retrieval scores select the bounded
   panel only; they are never labels, severity, confidence, or evidence that a
   relationship exists. Equal scores are source-balanced deterministically.
   One three-context MVP panel emits at most 16 questions; every omission is an
   explicit coverage gap, and exact pair narrowing is available for complete
   pair-specific coverage.
3. Resolve a reviewed, fresh model decision. Require account availability and
   product qualification for a release-qualified path.
4. Ask the content broker for the smallest decisive excerpts. Exclude raw
   credentials, detected secrets, script/executable bodies, unrelated files,
   escaping references, and withheld content.
5. Build a disclosure manifest containing provider, exact model/effort,
   selection digest, adapter/prompt/taxonomy versions, purpose, content
   handles, exclusions, retention/cache facts, and requested output contract.
6. For standalone invocation, display the manifest and require exact digest
   confirmation. For an explicit one-shot semantic run, record the manifest and
   use that request as one-run authorization for only the immediately generated
   digest. Neither path grants write authority or reusable/background permission.
7. Invoke analysts A and B concurrently in separate fresh ephemeral Codex
   contexts with no direct filesystem access and no credentials in payloads or
   logs. They are blind to one another, receive canonical/reversed source order,
   and each answers every frozen pair/dimension question exactly once.
   Each analyst also receives a compact identity table whose source, handle,
   allowed-claim, and dimension fields are a closed copy contract.
8. Validate both analyst responses, then invoke a third judge in a fresh context.
   It sees both completed answers, searches for counterexamples/missing evidence,
   and records consensus, resolved disagreement, challenge, or insufficiency.
9. Validate all three transport lifecycles, closed schemas/labels/recommendations,
   exact question/source/dimension joins, content-handle citations, secret
   echoes, source-order disclosure, and request/response identity. Invalid or
   uncited panel output is unusable.
10. Record all three model statements only as immutable `inferred` evidence.
11. Let the local adjudicator require corroborated analyst consensus, judge
    confirmation, closed counterexamples, no missing evidence, and a recommendation/label
    compatibility rule before it applies applicability, taxonomy,
    state, label, qualifier, severity, confidence, deduplication, and grouping.
    Even corroborated conflict or redundancy remains a candidate when the
    shared applicability region is not established. A judge-resolved analyst
    disagreement is at most a candidate and can never become a finding or pass.
12. Seal the same result graph used by the human terminal, Markdown, JSON, and
    CI projections.

### 6.2 Provider response contract

Each analyst may return one candidate relation per frozen question, cited
handles/claims, a concise rationale, shared-region assessment, distinct
contributions, counterexample status, missing evidence, and one bounded manual
recommendation candidate. The judge may corroborate consensus, resolve a
disagreement by selecting one analyst label, challenge both, or declare the
evidence insufficient. None of the three calls may set product check state, severity,
final confidence, authority, repair operations, scope, or evidence provenance.
Model agreement never becomes deterministic proof; judge resolution never hides
the underlying disagreement.

Recommendation kinds are a closed vocabulary. Local compatibility rules can
promote a corroborated candidate only into an `authority=none`,
`automatic_apply=false` next action with explicit expected benefit, risk, and
verification. Unknown, challenged, incompatible, or unverified recommendations
are discarded or replaced by a generic evidence request.

Prompt-like text inside analyzed files is quoted as untrusted data. It cannot
alter the system contract, add content handles, choose a model, request another
tool, grant permission, or change retention behavior.

### 6.3 Failure semantics

| Lifecycle point | Product behavior |
| --- | --- |
| Semantic mode disabled | Relevant semantic checks are `not_run`; deterministic graph remains usable |
| No reviewed/fresh/available/qualified route before start | `not_run` with the exact capability gap |
| Disclosure lacks decisive approved content | `insufficient_evidence`; no provider start |
| Standalone invocation digest absent or mismatched | `not_run`; zero provider requests |
| Request starts, then times out/transport fails | Affected check is `error`; prior results survive |
| Response is malformed, uncited, secret-echoing, or overreaching | Response is unusable; affected check is `error` or a safe redaction event |
| Completed evidence remains ambiguous | Local `insufficient_evidence` or bounded `candidate`; never a forced finding |
| Static evidence supports only a runtime selection hypothesis | `candidate` + `runtime_validation_needed`; no runtime claim |

Cross-run semantic response caching remains disabled. A later opt-in cache must
be local, retention-disclosed, and keyed by every identity listed in section 6.

## 7. Execution plan in reviewable slices

| Slice | Deliverable | Entry gate | Exit gate | Status |
| --- | --- | --- | --- | --- |
| 06-A | Reviewed model profile, offline resolver, official-source watcher, user override, MR suite | Stage 01–05 contracts | All retained MR cases pass; no implicit promotion/fallback | Implemented in working tree |
| 06-B | Production disclosure manifest and exact per-run authorization | 06-A | Secret/script exclusion, digest invalidation, and zero-call mismatch tests pass | Implemented locally |
| 06-C | Parallel blind-analyst plus judge Codex Desktop panel, schema/citation/recommendation validation, local adjudication bridge, human and sealed projections | 06-B | Concurrency, blindness, judge ordering/identity, disagreement downgrade, authority/citation gates, human-output and sealed-graph tests pass | Implemented, unqualified |
| 06-D | Development corpus, independent holdout, live synthetic canary, model/effort comparison | 06-C | Stage 04 sample sufficiency, absolute privacy gates, three isolated live passes | Blocked on corpus/review resources |
| 06-E | Local baseline/delta and private scheduled runs | Stable sealed semantic graph | Reproducible deltas, redacted export, no unattended repair | Planned |

Automatic repair remains out of scope. A semantic finding can feed only the
existing proposal/manual path until the complete Stage 04 repair matrix passes.

## 8. Executable test plan

### 8.1 Model-routing contract suite

`test-spec/scenarios/stage-06-model-routing-v0.1.json` is validated by
`test-spec/schema/model-routing-suite.schema.json` and executed with:

```sh
agent-doctor model spec --summary
```

The eleven retained MR cases cover:

- reviewed quality-first default and max effort;
- account availability without ranking;
- exact user pin and no silent substitution;
- unknown pin, mixed auto/pin, and stale profile refusal;
- qualification required for product semantics but not advisory review;
- explicit Sol/Terra/Luna capability tiers;
- unavailable default without fallback.

Code-level tests additionally prove source allowlisting, profile validation,
selection-digest invalidation, documentation candidate detection without
promotion, fetch failure as execution failure, and workflow/profile default
parity.

### 8.2 Semantic contract and integration tests

Stage 04 S-SEM-001–S-SEM-018 now execute without changing their oracles.
Regular CI uses local contract doubles and synthetic sentinel secrets. It
performs no live request and needs no API key. These are normative regression
checks, not the independent measurement corpus.

Required integration assertions include:

- one disclosed content handle cannot reveal another source;
- model/effort/profile/provider/content/purpose changes invalidate authorization;
- every accepted citation refers to a disclosed handle and exact revision;
- secret/script exclusions are checked in request, logs, reports, fingerprints,
  cache, and failure bundles;
- provider state/severity/authorization fields are rejected;
- analyst role/identity mismatches, missing judgments, invalid joins, and
  uncited judgments are rejected;
- tests prove the blind analysts overlap in time and the judge starts only after
  both validate;
- analyst disagreement is visible and downgraded instead of being hidden by
  majority voting;
- analyst B source order is reversed and prompt-injection text remains quoted data;
- recommendation kinds and label compatibility are locally constrained;
- local adjudication retains all model evidence as `inferred`;
- provider failure preserves deterministic cases and produces the correct
  run-level partial-result outcome; and
- all renderers remain projections of one sealed graph.

The expanded Stage 04 catalog currently executes 101 scenarios; 31 repair-
mutation/concurrency scenarios remain explicitly unsupported. This count is a
contract-runner status only and does not establish accuracy, usefulness,
calibration, or release readiness.

### 8.3 Live qualification tests

Live tests are manual or protected-environment only, use synthetic content,
require an exact disclosure manifest, and never run on untrusted pull requests.
They record provider, model, effort, selection/profile digest, adapter, prompt
contract, taxonomy, input digest, retry count, and safe request ID. Credentials
are never recorded.

Changing the default requires:

1. attributable official recommendation and capability evidence;
2. account-availability canary;
3. all absolute semantic/privacy/reproducibility gates;
4. the Stage 04 independent holdout protocol and minimum sample sizes;
5. comparison against the incumbent default on quality, stability, latency,
   and cost; and
6. reviewed profile and workflow changes in one pull request.

No accuracy, usefulness, calibration, or release claim is allowed before those
measurements exist.

## 9. CI/CD operating model

- Pull requests always run deterministic tests, Stage 04 contracts, and the
  model-routing suite without network or credentials.
- The optional Codex review remains advisory/read-only and is separately
  configured through repository variables and `OPENAI_API_KEY`.
- The weekly model-profile watcher accesses only official public documentation,
  has no API key, and cannot modify the repository.
- A future live semantic canary belongs in a protected manual workflow with
  synthetic fixtures, an environment-scoped secret, approvals, cost/time
  limits, and artifact redaction. It is never a deterministic correctness gate.
- Profile promotion, prompt changes, and qualification changes require pull-
  request review and invalidate prior qualification identity.

## 10. Binding safety decisions

1. Official docs nominate candidates; tests and review promote defaults.
2. `/v1/models` establishes availability only, never capability ranking.
3. `auto` is the default strategy; exact IDs remain replaceable profile data.
4. User pins are exact and fail closed; no silent substitution or effort
   downgrade occurs.
5. Advisory review and product semantic evidence are distinct trust paths.
6. Product semantic invocation requires exact disclosure authorization, minimization,
   adapter validation, inferred provenance, local adjudication, and
   qualification.
7. Ambiguous or apparently unrelated requests must be clarified before product
   scope changes are implemented.
8. Static Skill evidence still cannot prove runtime selection or causality.
9. Repairs remain proposal/manual-only.
