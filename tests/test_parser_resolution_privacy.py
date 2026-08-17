from __future__ import annotations

from pathlib import Path

from agent_doctor.parser import parse_source
from agent_doctor.privacy import SafeReader, minimize_excerpt, redact_secrets, safe_revision
from agent_doctor.resolution import (
    ReferenceDeclaration,
    explicit_version_compatibility,
    extract_references,
    resolve_reference,
)


def test_parser_preserves_modalities_qualifiers_and_inclusive_columns() -> None:
    parsed = parse_source(
        "source-test",
        "instruction",
        "Must run tests.\nPrefer concise output except for audits.\n",
    )
    assert {item.modality for item in parsed.claims} == {"required", "preferred"}
    assert any("except" in item.qualifiers for item in parsed.claims)
    first = next(item for item in parsed.claims if item.span["start_line"] == 1)
    assert first.span["end_column"] == len("Must run tests.")


def test_repeated_qualifiers_are_canonicalized_without_duplicates() -> None:
    parsed = parse_source(
        "source-test",
        "instruction",
        "If input is present, continue only if validation succeeds.\n",
    )
    assert parsed.claims
    assert all(item.qualifiers == ("if", "only") for item in parsed.claims)


def test_parser_preserves_crlf_unicode_byte_and_display_spans() -> None:
    parsed = parse_source("source-test", "instruction", "标题\r\n必须运行测试。\r\n")
    claim = next(item for item in parsed.claims if item.span["start_line"] == 2)
    assert claim.span == {
        "start_line": 2,
        "end_line": 2,
        "start_column": 1,
        "end_column": 7,
        "start_byte": 8,
        "end_byte": 29,
    }


def test_malformed_loose_metadata_is_partial_with_error() -> None:
    parsed = parse_source("source-test", "skill_manifest", "id: review\nmode: [unterminated\n")
    assert parsed.completeness == "partial"
    assert parsed.claims
    assert any(item.severity == "error" for item in parsed.diagnostics)


def test_reference_resolves_from_declaration_and_rejects_escape(tmp_path: Path) -> None:
    package = tmp_path / "repo/skills/a"
    target = package / "refs/policy.md"
    target.parent.mkdir(parents=True)
    target.write_text("schema: 1\n", encoding="utf-8")
    declaring = package / "SKILL.md"
    declaring.write_text("reference: refs/policy.md\n", encoding="utf-8")
    valid = resolve_reference(
        ReferenceDeclaration("refs/policy.md", 1, True, "source-a"),
        declaring_path=declaring,
        allowed_root=package,
        display_root=tmp_path / "repo",
    )
    escape = resolve_reference(
        ReferenceDeclaration("../../private/policy.md", 1, True, "source-a"),
        declaring_path=declaring,
        allowed_root=package,
        display_root=tmp_path / "repo",
    )
    assert valid.status == "valid"
    assert escape.status == "escape"
    assert escape.outside_read_attempted is False
    assert escape.normalized_target and not escape.normalized_target.startswith("/")


def test_freshness_uses_explicit_version_contract_not_age() -> None:
    assert explicit_version_compatibility(
        "required_policy_schema: 3\n", "schema: 3\n"
    )[0] == "compatible"
    assert explicit_version_compatibility(
        "required_policy_schema: 3\n",
        "schema: 2\nnot compatible with schema 3\n",
    )[0] == "incompatible"
    assert explicit_version_compatibility(
        "required_policy_schema: 3\n", "schema: 2\n"
    )[0] == "insufficient_evidence"
    status, reason = explicit_version_compatibility(
        "Read `references/policy.md`.\n", "schema: 1\n"
    )
    assert status == "no_contract"
    assert "required policy schema" in reason


def test_reference_extraction_accepts_paths_but_not_commands_or_prose() -> None:
    content = """Read `references/policy.md` before review.
Run `python \"<path-to-skill>/scripts/check.py\" --strict` when asked.
The `scripts/` directory contains optional helpers for local use.
See [the policy](references/review.md).
```sh
python scripts/check.py --all
```
"""
    declarations = extract_references("source-a", content)
    assert [(item.raw, item.line) for item in declarations] == [
        ("references/policy.md", 1),
        ("references/review.md", 4),
    ]


def test_reference_extraction_preserves_explicit_single_file_fallback() -> None:
    content = """本文件可以单独兜底；完整模式会补读 references/。
只有在单文件安装场景里，才停留在本文件的兜底规则。
完整说明见 [Policy](./references/policy.md)。
"""
    declarations = extract_references("source-a", content)
    assert len(declarations) == 1
    assert declarations[0].optional is True
    assert declarations[0].optional_basis == (
        "explicit single-file fallback contract in the declaring Skill"
    )


def test_single_file_fallback_is_bound_to_its_named_reference() -> None:
    content = """Single-file fallback may omit [examples](references/examples.md).
MUST read [security](references/security.md); startup fails without it.
"""
    declarations = extract_references("source-a", content)
    by_raw = {item.raw: item for item in declarations}
    assert by_raw["references/examples.md"].optional is True
    assert by_raw["references/security.md"].optional is False
    assert by_raw["references/security.md"].required is True


def test_conditional_chinese_navigation_is_optional_but_must_is_not() -> None:
    content = """想看场景样本评测：看 [样本](./evals/real-samples.md)。
必须先读取 [安全规则](./references/security.md)。
"""
    declarations = extract_references("source-a", content)
    by_raw = {item.raw: item for item in declarations}
    assert by_raw["./evals/real-samples.md"].optional is True
    assert by_raw["./references/security.md"].optional is False


def test_reference_extraction_abstains_on_non_path_code_tokens() -> None:
    content = """Use \x60.xlsx\x60 for output.
Use \x60$Spreadsheets\x60 for workbook work.
Use \x60@oai/artifact-tool\x60 for authoring.
Read the applicable \x60AGENTS.md\x60 before editing.
The conversation URL must contain \x60/c/\x60.
Open PRs before following \x60../yeet/SKILL.md\x60.
Only after setup may the agent read \x60private/generated.jsonl\x60.
Read \x60docs/project-runbook.md\x60 from the selected workspace.
Inspect \x60assets/source\x60 in the generated output.
"""
    assert extract_references("source-a", content) == ()


def test_reference_directory_is_a_valid_in_scope_target(tmp_path: Path) -> None:
    package = tmp_path / "repo/skills/a"
    target = package / "references"
    target.mkdir(parents=True)
    declaring = package / "SKILL.md"
    declaring.write_text("Read `references/` before review.\n", encoding="utf-8")
    result = resolve_reference(
        ReferenceDeclaration("references/", 1, True, "source-a"),
        declaring_path=declaring,
        allowed_root=package,
        display_root=tmp_path / "repo",
    )
    assert result.status == "valid_directory"
    assert result.target_path == target


def test_reference_follows_only_in_scope_symlink(tmp_path: Path) -> None:
    package = tmp_path / "repo/skills/a"
    package.mkdir(parents=True)
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "policy.md").write_text("secret outside", encoding="utf-8")
    (package / "refs").symlink_to(outside, target_is_directory=True)
    declaration = package / "SKILL.md"
    declaration.write_text("reference: refs/policy.md\n", encoding="utf-8")
    result = resolve_reference(
        ReferenceDeclaration("refs/policy.md", 1, True, "source-a"),
        declaring_path=declaration,
        allowed_root=package,
        display_root=tmp_path / "repo",
    )
    assert result.status == "escape"
    assert result.outside_read_attempted is False


def test_unknown_reference_forms_abstain_as_unsupported(tmp_path: Path) -> None:
    package = tmp_path / "repo/skills/a"
    package.mkdir(parents=True)
    declaration = package / "SKILL.md"
    declaration.write_text("synthetic\n", encoding="utf-8")
    for raw in ("~/policy.md", "%MYSTERY%/policy.md", "s3://bucket/policy.md"):
        result = resolve_reference(
            ReferenceDeclaration(raw, 1, True, "source-a"),
            declaring_path=declaration,
            allowed_root=package,
            display_root=tmp_path / "repo",
        )
        assert result.status == "unsupported"
        assert result.outside_read_attempted is False


def test_secret_redaction_and_script_exclusion(tmp_path: Path) -> None:
    sentinel = "SYNTHETIC_SECRET_DO_NOT_SEND"
    content = f"TOKEN={sentinel}\n"
    redacted = redact_secrets(content)
    revision, categories = safe_revision(content)
    excerpt, excerpt_categories, disclosure = minimize_excerpt(content)
    assert sentinel not in redacted.text
    assert sentinel not in revision
    assert sentinel not in excerpt
    assert categories and excerpt_categories
    assert disclosure == "redacted"

    script = tmp_path / "check.sh"
    script.write_text("touch should-not-run\n", encoding="utf-8")
    result = SafeReader().read_text(
        script,
        allowed_root=tmp_path,
        purpose="analysis",
        source_type="script",
        inspection="metadata_only",
    )
    assert result.status == "withheld"
    assert result.content is None


def test_absolute_home_paths_are_redacted_from_claims_and_config_dimensions() -> None:
    home = str(Path.home().resolve(strict=False))
    instruction = parse_source(
        "source-home",
        "instruction",
        f"Read {home}/private/policy.md before review.\n",
    )
    config = parse_source(
        "source-config",
        "config",
        f'["{home}/private/skill"]\nenabled = true\n',
    )
    rendered = repr((instruction.claims, config.claims))
    assert home not in rendered
    assert "user://private" in rendered


def test_bounded_reader_keeps_valid_unicode_prefix_when_limit_splits_scalar(tmp_path: Path) -> None:
    path = tmp_path / "unicode.md"
    path.write_text("abc界tail", encoding="utf-8")
    result = SafeReader(max_bytes=5).read_text(
        path,
        allowed_root=tmp_path,
        purpose="analysis",
        source_type="instruction",
    )
    assert result.status == "partial"
    assert result.content == "abc"
    assert result.truncated is True
