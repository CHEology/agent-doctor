"""Command-line interface for the Codex-first local MVP."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Never, Sequence

from .analysis import AnalysisRequest, analyze
from .ci import CIPolicy, evaluate_ci, exit_code as ci_exit_code
from .openai_models import (
    ModelSelectionRequest,
    check_official_model_profile,
    load_model_profile,
    parse_available_models,
    resolve_model,
    run_model_routing_suite,
)
from .proposal import build_manual_proposal
from .privacy import redact_secrets
from .render import render_debug_terminal, render_json, render_markdown, render_terminal
from .scenario import SuitePaths, report_exit_code, run_suite, validate_suite_file
from .semantic_workflow import (
    build_semantic_package,
    extract_invocation_response,
    invoke_codex_provider,
    resolve_codex_selection,
)
from .version import __version__


EXIT_OK = 0
EXIT_POLICY_FAILED = 2
EXIT_EXECUTION_FAILED = 3
EXIT_USAGE = 64


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"agent-doctor: error: {message}\n")


def _default_spec_root() -> Path:
    candidate = Path.cwd() / "test-spec"
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = ArgumentParser(prog="agent-doctor", description="Offline-first Codex configuration diagnostics")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan a local workspace and project one sealed result")
    scan.add_argument("workspace", nargs="?", default=".", help="workspace root (default: current directory)")
    scan.add_argument("--selected", help="selected file or directory inside the workspace")
    scan.add_argument(
        "--include-user",
        action="store_true",
        help=(
            "include user Codex configuration, documented user Skills, and supplemental local "
            "Codex-home/plugin-cache Skill inventory (runtime activation remains unobserved)"
        ),
    )
    scan.add_argument("--include-system", action="store_true", help="include selected /etc/codex sources")
    scan.add_argument("--project-trust", choices=("trusted", "untrusted", "unknown"), default="unknown")
    scan.add_argument(
        "--semantic-mode",
        choices=("disabled", "enabled"),
        default="disabled",
        help="enable semantic workflow coverage (a consented semantic submission is a separate step)",
    )
    scan.add_argument("--profile", type=Path, help="reviewed local Codex platform-profile JSON")
    scan.add_argument(
        "--format",
        choices=("terminal", "debug", "markdown", "json", "ci"),
        default="terminal",
        help="terminal is human-first; debug is the compact ID-oriented view",
    )
    scan.add_argument("--output", type=Path, help="write the selected projection to this path instead of stdout")
    scan.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "info"), default="high")
    scan.add_argument("--minimum-confidence", choices=("high", "medium", "low"))
    scan.add_argument("--required-family", action="append", default=[], help="CI-required check family (repeatable)")
    scan.add_argument("--candidates-block", action="store_true", help="allow candidates to block CI using potential severity")
    scan.add_argument("--ci", action="store_true", help="evaluate CI policy even when another renderer is selected")

    propose = subparsers.add_parser("propose", help="create a non-executable manual proposal from a sealed result")
    propose.add_argument("result", type=Path, help="sealed Agent Doctor result JSON")
    propose.add_argument("--case", action="append", dest="case_refs", required=True, help="finding/candidate case ID (repeatable)")
    propose.add_argument("--output", type=Path)

    spec = subparsers.add_parser("spec", help="validate or run Stage 04 scenario suites")
    spec_commands = spec.add_subparsers(dest="spec_command", required=True)
    validate_parser = spec_commands.add_parser("validate", help="validate a scenario suite against its schema")
    validate_parser.add_argument("suite", type=Path)
    validate_parser.add_argument("--schema", type=Path, default=_default_spec_root() / "schema/scenario-suite.schema.json")
    validate_parser.add_argument("--output", type=Path)

    run_parser = spec_commands.add_parser("run", help="execute supported scenarios and compare typed expectations")
    run_parser.add_argument("suite", type=Path)
    run_parser.add_argument("--schema", type=Path, default=_default_spec_root() / "schema/scenario-suite.schema.json")
    run_parser.add_argument("--golden", type=Path, default=_default_spec_root() / "fixtures/golden-v0.1.json")
    run_parser.add_argument("--id", action="append", dest="case_ids", help="run only this scenario ID (repeatable)")
    run_parser.add_argument("--repetitions", type=int, default=3, help="golden deterministic repetitions (default: 3)")
    run_parser.add_argument("--require-all", action="store_true", help="treat unsupported scenarios as execution failure")
    run_parser.add_argument("--output", type=Path)
    run_parser.add_argument("--summary", action="store_true", help="emit compact summary instead of every case record")

    model = subparsers.add_parser("model", help="inspect the reviewed OpenAI model-routing policy")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    model_resolve = model_commands.add_parser("resolve", help="resolve one capability without calling a provider")
    model_resolve.add_argument("--profile", type=Path, help="reviewed OpenAI model-capability profile JSON")
    model_resolve.add_argument("--capability", default="codex.advisory_review")
    model_resolve.add_argument("--strategy", choices=("auto", "pinned"), default="auto")
    model_resolve.add_argument("--model", dest="requested_model", help="exact user pin; requires --strategy pinned")
    model_resolve.add_argument(
        "--reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
    )
    model_resolve.add_argument(
        "--available-model",
        action="append",
        default=[],
        help="account-visible model ID from GET /v1/models (repeatable)",
    )
    model_resolve.add_argument("--available-models-json", type=Path, help="saved GET /v1/models response")
    model_resolve.add_argument("--require-qualified", action="store_true", help="require Stage 04 product-semantic qualification")
    model_resolve.add_argument("--require-ready", action="store_true", help="exit 3 unless availability and qualification requirements are met")
    model_resolve.add_argument("--as-of", help="injected RFC 3339 full-date for reproducible profile-freshness checks")
    model_resolve.add_argument("--output", type=Path)

    model_check = model_commands.add_parser(
        "check-official",
        help="explicitly fetch allowlisted official Markdown and report profile drift",
    )
    model_check.add_argument("--profile", type=Path, help="reviewed OpenAI model-capability profile JSON")
    model_check.add_argument("--output", type=Path)

    model_spec = model_commands.add_parser("spec", help="run the executable Stage 06 model-routing contract suite")
    model_spec.add_argument(
        "suite",
        type=Path,
        nargs="?",
        default=_default_spec_root() / "scenarios/stage-06-model-routing-v0.1.json",
    )
    model_spec.add_argument(
        "--schema",
        type=Path,
        default=_default_spec_root() / "schema/model-routing-suite.schema.json",
    )
    model_spec.add_argument("--profile", type=Path)
    model_spec.add_argument("--summary", action="store_true")
    model_spec.add_argument("--output", type=Path)

    semantic = subparsers.add_parser(
        "semantic",
        help="prepare, invoke, and locally adjudicate a consented Codex semantic run",
    )
    semantic_commands = semantic.add_subparsers(
        dest="semantic_command", required=True
    )
    semantic_prepare = semantic_commands.add_parser(
        "prepare",
        help="build an exact minimized disclosure manifest without calling a model",
    )
    semantic_prepare.add_argument("workspace", nargs="?", default=".")
    semantic_prepare.add_argument("--selected")
    semantic_prepare.add_argument("--include-user", action="store_true")
    semantic_prepare.add_argument("--include-system", action="store_true")
    semantic_prepare.add_argument(
        "--project-trust",
        choices=("trusted", "untrusted", "unknown"),
        default="unknown",
    )
    semantic_prepare.add_argument(
        "--profile", type=Path, help="reviewed Codex platform-profile JSON"
    )
    semantic_prepare.add_argument(
        "--source",
        action="append",
        default=[],
        help="exact selected Skill source ID or displayed location (repeatable)",
    )
    semantic_prepare.add_argument(
        "--purpose",
        default=(
            "Assess material semantic conflicts, scope overlap, behavioral "
            "redundancy, and complementarity among the selected Skills."
        ),
    )
    semantic_prepare.add_argument(
        "--capability", default="semantic.reasoning_quality_first"
    )
    semantic_prepare.add_argument(
        "--strategy", choices=("auto", "pinned"), default="auto"
    )
    semantic_prepare.add_argument("--model", dest="requested_model")
    semantic_prepare.add_argument(
        "--reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
    )
    semantic_prepare.add_argument(
        "--model-profile", type=Path, help="reviewed OpenAI model profile JSON"
    )
    semantic_prepare.add_argument(
        "--as-of", help="injected RFC 3339 full-date for reproducible profile checks"
    )
    semantic_prepare.add_argument("--output", type=Path)

    semantic_invoke = semantic_commands.add_parser(
        "invoke",
        help="invoke signed-in Codex only after exact manifest-digest consent",
    )
    semantic_invoke.add_argument("package", type=Path)
    semantic_invoke.add_argument("--consent-digest", required=True)
    semantic_invoke.add_argument("--output", type=Path)

    semantic_finalize = semantic_commands.add_parser(
        "finalize",
        help="validate a provider response and seal local final adjudication",
    )
    semantic_finalize.add_argument("workspace")
    semantic_finalize.add_argument("package", type=Path)
    semantic_finalize.add_argument("invocation", type=Path)
    semantic_finalize.add_argument("--consent-digest", required=True)
    semantic_finalize.add_argument("--selected")
    semantic_finalize.add_argument("--include-user", action="store_true")
    semantic_finalize.add_argument("--include-system", action="store_true")
    semantic_finalize.add_argument(
        "--project-trust",
        choices=("trusted", "untrusted", "unknown"),
        default="unknown",
    )
    semantic_finalize.add_argument("--profile", type=Path)
    semantic_finalize.add_argument(
        "--format", choices=("terminal", "debug", "markdown", "json"), default="terminal"
    )
    semantic_finalize.add_argument("--output", type=Path)
    return parser


def _write(text: str, path: Path | None) -> None:
    if path is None:
        sys.stdout.write(text)
        return
    path = path.expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _error_payload(code: str, message: str) -> str:
    safe_message = redact_secrets(message).text
    home = str(Path.home().resolve(strict=False))
    workspace = str(Path.cwd().resolve(strict=False))
    safe_message = safe_message.replace(workspace, "workspace://").replace(home, "user://")
    return json.dumps(
        {"schema_version": "agent-doctor-cli-error/0.1", "outcome": "execution_failed", "code": code, "message": safe_message},
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"


def _scan(args: argparse.Namespace) -> int:
    try:
        workspace = Path(args.workspace)
        selected = Path(args.selected) if args.selected else None
        if selected is not None and not selected.is_absolute():
            selected = workspace / selected
        response = analyze(
            AnalysisRequest(
                workspace=workspace,
                selected_path=selected,
                include_user=args.include_user,
                include_system=args.include_system,
                project_trust=args.project_trust,
                semantic_mode=args.semantic_mode,
                profile_path=args.profile,
            )
        )
        graph = response.graph
        required = tuple(args.required_family) or ("inventory",)
        policy = CIPolicy(
            fail_at_or_above=args.fail_on,
            minimum_confidence=args.minimum_confidence,
            required_families=required,
            candidates_block=args.candidates_block,
        )
        decision = evaluate_ci(graph, policy) if args.ci or args.format == "ci" else None
        if args.format == "terminal":
            text = render_terminal(graph)
            if decision is not None:
                text += f"CI: {decision['outcome']} ({decision['decision_id']})\n"
        elif args.format == "debug":
            text = render_debug_terminal(graph)
            if decision is not None:
                text += f"CI: {decision['outcome']} ({decision['decision_id']})\n"
        elif args.format == "markdown":
            text = render_markdown(graph)
            if decision is not None:
                text += f"\n## CI decision\n\n`{decision['outcome']}` (`{decision['decision_id']}`)\n"
        elif args.format == "json":
            text = render_json(graph)
        else:
            # The CI envelope keeps the durable graph intact; threshold
            # filtering changes only the decision view.
            text = json.dumps(
                {"schema_version": "agent-doctor-ci-envelope/0.1", "decision": decision, "result": graph},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n"
        _write(text, args.output)
        if decision is not None:
            return ci_exit_code(decision)
        return EXIT_EXECUTION_FAILED if graph.get("run", {}).get("outcome") == "execution_failed" or not graph.get("sealed") else EXIT_OK
    except Exception as exc:
        sys.stderr.write(_error_payload("scan_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED


def _spec_validate(args: argparse.Namespace) -> int:
    report = validate_suite_file(SuitePaths(args.suite, args.schema))
    try:
        _write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
    except OSError as exc:
        sys.stderr.write(_error_payload("output_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED
    return EXIT_OK if report["valid"] else EXIT_EXECUTION_FAILED


def _propose(args: argparse.Namespace) -> int:
    try:
        graph = json.loads(args.result.read_text(encoding="utf-8"))
        proposal = build_manual_proposal(graph, args.case_refs)
        _write(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(_error_payload("proposal_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report[key]
        for key in (
            "schema_version",
            "scenario_schema_version",
            "product_version",
            "suite_id",
            "suite_version",
            "suite_kind",
            "evidence_outcome",
            "gate_outcome",
            "counts",
            "measurement_status",
            "measurement_note",
        )
        if key in report
    }


def _spec_run(args: argparse.Namespace) -> int:
    if args.repetitions < 1 or args.repetitions > 20:
        sys.stderr.write(_error_payload("invalid_repetitions", "repetitions must be between 1 and 20"))
        return EXIT_USAGE
    report = run_suite(
        SuitePaths(args.suite, args.schema, args.golden),
        selected_ids=set(args.case_ids) if args.case_ids else None,
        repetitions=args.repetitions,
        require_all=args.require_all,
    )
    payload = _compact_report(report) if args.summary else report
    try:
        _write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
    except OSError as exc:
        sys.stderr.write(_error_payload("output_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED
    return report_exit_code(report)


def _model_resolve(args: argparse.Namespace) -> int:
    try:
        profile = load_model_profile(args.profile)
        available: set[str] | None = set(args.available_model) if args.available_model else None
        if args.available_models_json is not None:
            payload = json.loads(args.available_models_json.read_text(encoding="utf-8"))
            from_response = set(parse_available_models(payload))
            available = from_response if available is None else available | from_response
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        decision = resolve_model(
            profile,
            ModelSelectionRequest(
                capability=args.capability,
                strategy=args.strategy,
                requested_model=args.requested_model,
                reasoning_effort=args.reasoning_effort,
                available_models=frozenset(available) if available is not None else None,
                require_qualified=args.require_qualified,
            ),
            as_of=as_of,
        )
        _write(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
        if decision["outcome"] != "selected":
            return EXIT_EXECUTION_FAILED
        if args.require_ready and not decision["invocation_ready"]:
            return EXIT_EXECUTION_FAILED
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(_error_payload("model_resolution_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED


def _model_check_official(args: argparse.Namespace) -> int:
    try:
        report = check_official_model_profile(load_model_profile(args.profile))
        _write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
        if report["outcome"] == "current":
            return EXIT_OK
        if report["outcome"] == "candidate_change":
            return EXIT_POLICY_FAILED
        return EXIT_EXECUTION_FAILED
    except Exception as exc:
        sys.stderr.write(_error_payload("official_model_check_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED


def _model_spec(args: argparse.Namespace) -> int:
    try:
        suite = json.loads(args.suite.read_text(encoding="utf-8"))
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        report = run_model_routing_suite(suite, schema, load_model_profile(args.profile))
        if args.summary:
            payload = {
                key: report[key]
                for key in (
                    "schema_version",
                    "suite_id",
                    "suite_version",
                    "evidence_outcome",
                    "gate_outcome",
                    "counts",
                    "measurement_status",
                    "measurement_note",
                )
                if key in report
            }
        else:
            payload = report
        _write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.output)
        if report["evidence_outcome"] == "execution_failed":
            return EXIT_EXECUTION_FAILED
        if report["gate_outcome"] == "policy_failed":
            return EXIT_POLICY_FAILED
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(_error_payload("model_spec_failed", f"{type(exc).__name__}: {exc}"))
        return EXIT_EXECUTION_FAILED


def _semantic_prepare(args: argparse.Namespace) -> int:
    try:
        workspace = Path(args.workspace)
        selected = Path(args.selected) if args.selected else None
        if selected is not None and not selected.is_absolute():
            selected = workspace / selected
        graph = analyze(
            AnalysisRequest(
                workspace=workspace,
                selected_path=selected,
                include_user=args.include_user,
                include_system=args.include_system,
                project_trust=args.project_trust,
                semantic_mode="enabled",
                profile_path=args.profile,
            )
        ).graph
        if not graph.get("sealed"):
            raise ValueError("deterministic preparation graph did not seal")
        observed_on = date.fromisoformat(args.as_of) if args.as_of else None
        selection = resolve_codex_selection(
            model_profile_path=args.model_profile,
            capability=args.capability,
            strategy=args.strategy,
            requested_model=args.requested_model,
            reasoning_effort=args.reasoning_effort,
            observed_on=observed_on,
        )
        package = build_semantic_package(
            graph,
            source_selectors=tuple(args.source),
            selection=selection,
            purpose=args.purpose,
        )
        _write(
            json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            args.output,
        )
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(
            _error_payload(
                "semantic_prepare_failed", f"{type(exc).__name__}: {exc}"
            )
        )
        return EXIT_EXECUTION_FAILED


def _semantic_invoke(args: argparse.Namespace) -> int:
    try:
        package = json.loads(args.package.read_text(encoding="utf-8"))
        result = invoke_codex_provider(
            package,
            consent_digest=args.consent_digest,
        )
        _write(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            args.output,
        )
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(
            _error_payload(
                "semantic_invoke_failed", f"{type(exc).__name__}: {exc}"
            )
        )
        return EXIT_EXECUTION_FAILED


def _semantic_finalize(args: argparse.Namespace) -> int:
    try:
        package = json.loads(args.package.read_text(encoding="utf-8"))
        manifest = package["manifest"]
        invocation_payload = json.loads(
            args.invocation.read_text(encoding="utf-8")
        )
        invocation, semantic_response = extract_invocation_response(
            invocation_payload
        )
        workspace = Path(args.workspace)
        selected = Path(args.selected) if args.selected else None
        if selected is not None and not selected.is_absolute():
            selected = workspace / selected
        graph = analyze(
            AnalysisRequest(
                workspace=workspace,
                selected_path=selected,
                include_user=args.include_user,
                include_system=args.include_system,
                project_trust=args.project_trust,
                semantic_mode="enabled",
                profile_path=args.profile,
                semantic_manifest=manifest,
                semantic_invocation=invocation,
                semantic_response=semantic_response,
                semantic_consent_digest=args.consent_digest,
            )
        ).graph
        if args.format == "terminal":
            rendered = render_terminal(graph)
        elif args.format == "debug":
            rendered = render_debug_terminal(graph)
        elif args.format == "markdown":
            rendered = render_markdown(graph)
        else:
            rendered = render_json(graph)
        _write(rendered, args.output)
        if not graph.get("sealed") or graph.get("run", {}).get("outcome") == "execution_failed":
            return EXIT_EXECUTION_FAILED
        return EXIT_OK
    except Exception as exc:
        sys.stderr.write(
            _error_payload(
                "semantic_finalize_failed", f"{type(exc).__name__}: {exc}"
            )
        )
        return EXIT_EXECUTION_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return _scan(args)
    if args.command == "propose":
        return _propose(args)
    if args.command == "spec" and args.spec_command == "validate":
        return _spec_validate(args)
    if args.command == "spec" and args.spec_command == "run":
        return _spec_run(args)
    if args.command == "model" and args.model_command == "resolve":
        return _model_resolve(args)
    if args.command == "model" and args.model_command == "check-official":
        return _model_check_official(args)
    if args.command == "model" and args.model_command == "spec":
        return _model_spec(args)
    if args.command == "semantic" and args.semantic_command == "prepare":
        return _semantic_prepare(args)
    if args.command == "semantic" and args.semantic_command == "invoke":
        return _semantic_invoke(args)
    if args.command == "semantic" and args.semantic_command == "finalize":
        return _semantic_finalize(args)
    parser.error("unknown command")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
