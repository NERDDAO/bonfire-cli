"""Tests for profile CLI commands and OWL export/import."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from bonfires.cli import cli


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "BONFIRE_API_URL": "http://localhost:9999",
        "BONFIRE_ID": "test-bonfire",
        "BONFIRE_AGENT_ID": "test-agent",
        "BONFIRE_API_KEY": "test-key",
        "BONFIRE_VAULT_DIR": str(tmp_path),
    }


def _create_kengram(runner: CliRunner, name: str = "Test KE") -> str:
    """Create a kEngram and return its ID."""
    result = runner.invoke(cli, ["kengram", "new", name, "--json"])
    data = json.loads(result.output)
    return data["id"]


# ---------------------------------------------------------------------------
# profile new / list / show
# ---------------------------------------------------------------------------


def test_profile_new(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, ["kengram", "profile", "new", "Schema.org"])
    assert result.exit_code == 0
    assert "Created" in result.output
    assert "profile-schema-org" in result.output


def test_profile_new_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, ["kengram", "profile", "new", "FOAF", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "created"
    assert data["id"] == "profile-foaf"


def test_profile_new_with_namespace(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, [
        "kengram", "profile", "new", "Custom",
        "--namespace", "foaf=http://xmlns.com/foaf/0.1/",
        "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "profile-custom"


def test_profile_new_bad_namespace(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, [
        "kengram", "profile", "new", "Bad",
        "--namespace", "no-equals-sign",
    ])
    assert result.exit_code == 0  # graceful error, not crash
    assert "Invalid namespace" in result.output


def test_profile_list_empty(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, ["kengram", "profile", "list"])
    assert result.exit_code == 0
    assert "No profiles" in result.output


def test_profile_list_with_items(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    runner.invoke(cli, ["kengram", "profile", "new", "Alpha"])
    runner.invoke(cli, ["kengram", "profile", "new", "Beta"])
    result = runner.invoke(cli, ["kengram", "profile", "list"])
    assert result.exit_code == 0
    assert "Alpha" in result.output
    assert "Beta" in result.output


def test_profile_list_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    runner.invoke(cli, ["kengram", "profile", "new", "Gamma"])
    result = runner.invoke(cli, ["kengram", "profile", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["profiles"]) == 1
    assert data["profiles"][0]["id"] == "profile-gamma"


def test_profile_show(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    runner.invoke(cli, ["kengram", "profile", "new", "ShowMe"])
    result = runner.invoke(cli, ["kengram", "profile", "show", "profile-showme"])
    assert result.exit_code == 0
    assert "ShowMe" in result.output


def test_profile_show_not_found(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    result = runner.invoke(cli, ["kengram", "profile", "show", "profile-nope"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_profile_show_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    runner.invoke(cli, ["kengram", "profile", "new", "Detail"])
    result = runner.invoke(cli, ["kengram", "profile", "show", "profile-detail", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "profile-detail"
    assert "ke" in data["namespaces"]


# ---------------------------------------------------------------------------
# profile attach / detach
# ---------------------------------------------------------------------------


def test_profile_attach(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Attached"])
    result = runner.invoke(cli, ["kengram", "profile", "attach", "profile-attached"])
    assert result.exit_code == 0
    assert "Attached" in result.output


def test_profile_attach_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    ke_id = _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "AttachJ"])
    result = runner.invoke(cli, [
        "kengram", "profile", "attach", "profile-attachj", "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "attached"
    assert data["kengram_id"] == ke_id


def test_profile_attach_duplicate(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Dup"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-dup"])
    result = runner.invoke(cli, ["kengram", "profile", "attach", "profile-dup"])
    assert result.exit_code == 0
    assert "already attached" in result.output


def test_profile_attach_not_found(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "profile", "attach", "profile-missing"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_profile_detach(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "DetachMe"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-detachme"])
    result = runner.invoke(cli, ["kengram", "profile", "detach", "profile-detachme"])
    assert result.exit_code == 0
    assert "Detached" in result.output


def test_profile_detach_not_attached(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "profile", "detach", "profile-nope"])
    assert result.exit_code == 0
    assert "not attached" in result.output


# ---------------------------------------------------------------------------
# profile validate / suggest / gaps
# ---------------------------------------------------------------------------


def test_profile_validate_no_profiles(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "profile", "validate"])
    assert result.exit_code == 0
    assert "No ontology profiles" in result.output


def test_profile_validate_ok(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Validate"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-validate"])
    result = runner.invoke(cli, ["kengram", "profile", "validate"])
    assert result.exit_code == 0
    assert "No violations" in result.output


def test_profile_validate_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "ValJ"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-valj"])
    result = runner.invoke(cli, ["kengram", "profile", "validate", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "validated"
    assert data["violation_count"] == 0


def test_profile_suggest_no_profiles(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "profile", "suggest"])
    assert result.exit_code == 0
    assert "No profiles" in result.output


def test_profile_suggest_with_profiles(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Sug1"])
    result = runner.invoke(cli, ["kengram", "profile", "suggest", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "suggestions" in data
    assert len(data["suggestions"]) == 1


def test_profile_gaps_no_profiles(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "profile", "gaps"])
    assert result.exit_code == 0
    assert "No ontology profiles" in result.output


def test_profile_gaps_ok(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Gaps"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-gaps"])
    result = runner.invoke(cli, ["kengram", "profile", "gaps", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["gap_count"] == 0


# ---------------------------------------------------------------------------
# export --format owl
# ---------------------------------------------------------------------------


def test_export_owl_no_profiles(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    result = runner.invoke(cli, ["kengram", "export", "--format", "owl"])
    assert result.exit_code == 0
    assert "No ontology profiles" in result.output


def test_export_owl_json(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "OwlExp"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-owlexp"])
    result = runner.invoke(cli, [
        "kengram", "export", "--format", "owl", "--serialization", "turtle", "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "exported"
    assert data["serialization"] == "turtle"
    assert data["path"].endswith(".ttl")


def test_export_owl_jsonld(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "OwlJLD"])
    runner.invoke(cli, ["kengram", "profile", "attach", "profile-owljld"])
    result = runner.invoke(cli, [
        "kengram", "export", "--format", "owl", "--serialization", "json-ld", "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["path"].endswith(".jsonld")


# ---------------------------------------------------------------------------
# import-owl
# ---------------------------------------------------------------------------


def test_import_owl(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    runner.invoke(cli, ["kengram", "profile", "new", "Imp"])

    # Write the profile with a class_map so inversion works
    import json as _json
    profile_path = tmp_path / "kengrams" / "profiles" / "profile-imp.json"
    profile_data = _json.loads(profile_path.read_text())
    profile_data["class_map"] = {
        "Person": {"owl_class": "http://xmlns.com/foaf/0.1/Person"},
    }
    profile_data["namespaces"]["foaf"] = "http://xmlns.com/foaf/0.1/"
    profile_path.write_text(_json.dumps(profile_data, indent=2))

    # Create a minimal Turtle file
    ttl_file = tmp_path / "test.ttl"
    ttl_file.write_text(
        "@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<http://example.org/alice> a foaf:Person ; rdfs:label \"Alice\" .\n"
        "<http://example.org/bob> a foaf:Person ; rdfs:label \"Bob\" .\n"
    )

    result = runner.invoke(cli, [
        "kengram", "import-owl", str(ttl_file),
        "--profile", "profile-imp", "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "imported"
    assert data["nodes_added"] == 2


def test_import_owl_profile_not_found(tmp_path: Path) -> None:
    runner = CliRunner(env=_env(tmp_path))
    _create_kengram(runner)
    ttl_file = tmp_path / "empty.ttl"
    ttl_file.write_text("")
    result = runner.invoke(cli, [
        "kengram", "import-owl", str(ttl_file),
        "--profile", "profile-nope",
    ])
    assert result.exit_code == 0
    assert "not found" in result.output
