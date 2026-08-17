from __future__ import annotations

from pathlib import Path

from agent_doctor.parser import parse_source
from agent_doctor.privacy import SafeReader, minimize_excerpt, redact_secrets, safe_revision
from agent_doctor.resolution import ReferenceDeclaration, resolve_reference


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
