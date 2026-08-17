"""Command-line interface for the Codex-first local MVP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Never, Sequence

from .analysis import AnalysisRequest, analyze
from .ci import CIPolicy, evaluate_ci, exit_code as ci_exit_code
from .proposal import build_manual_proposal
from .privacy import redact_secrets
from .render import render_json, render_markdown, render_terminal
from .scenario import SuitePaths, report_exit_code, run_suite, validate_suite_file
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
    scan.add_argument("--profile", type=Path, help="reviewed local Codex platform-profile JSON")
    scan.add_argument("--format", choices=("terminal", "markdown", "json", "ci"), default="terminal")
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
                semantic_mode="disabled",
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
    parser.error("unknown command")
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
