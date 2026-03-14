"""Integration tests for kengram CLI commands using Click CliRunner."""

from unittest.mock import patch

from click.testing import CliRunner
from bonfires.cli import cli


def _env_overrides(tmp_path):
    return {
        "BONFIRE_API_URL": "http://localhost:9999",
        "BONFIRE_ID": "test-bonfire",
        "BONFIRE_AGENT_ID": "test-agent",
        "BONFIRE_API_KEY": "test-key",
        "BONFIRE_VAULT_DIR": str(tmp_path),
    }


def test_kengram_new(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "new", "Test Session"])
    assert result.exit_code == 0
    assert "Created" in result.output
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    assert len(manifests) == 1


def test_kengram_list_empty(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "list"])
    assert result.exit_code == 0
    assert "No kEngrams" in result.output


def test_kengram_list_with_items(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "First"])
    runner.invoke(cli, ["kengram", "new", "Second", "--type", "topic"])
    result = runner.invoke(cli, ["kengram", "list"])
    assert result.exit_code == 0
    assert "First" in result.output
    assert "Second" in result.output


def test_kengram_show(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Show Test"])
    result = runner.invoke(cli, ["kengram", "show"])
    assert result.exit_code == 0
    assert "Show Test" in result.output


def test_kengram_summary(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Sum Test"])
    result = runner.invoke(cli, ["kengram", "summary", "Updated summary"])
    assert result.exit_code == 0
    assert "Updated" in result.output


def test_kengram_use(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "use", "--help"])
    assert result.exit_code == 0


def test_kengram_delete_force(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Delete Me"])
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    assert len(manifests) == 1
    kengram_id = manifests[0].stem
    result = runner.invoke(cli, ["kengram", "delete", kengram_id, "--force"])
    assert result.exit_code == 0
    assert "Deleted" in result.output
    manifests_after = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    assert len(manifests_after) == 0


def test_kengram_delete_not_found(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "delete", "ke-nonexistent", "--force"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_kengram_export(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Export Test"])
    result = runner.invoke(cli, ["kengram", "export"])
    assert result.exit_code == 0
    assert "Exported" in result.output or "canvas" in result.output.lower()
    canvas_files = list((tmp_path / "kengrams" / "canvas").glob("*.canvas"))
    assert len(canvas_files) == 1


def test_pin_with_uuid_fetches_entity(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Pin Fetch Test"])
    fake_entity = {
        "uuid": "abc-123",
        "name": "Fetched Entity",
        "summary": "A summary from the API",
        "labels": ["concept", "test"],
    }
    with patch("bonfires.kengram.commands.kg_client") as mock_kg:
        mock_kg.fetch_entity.return_value = fake_entity
        result = runner.invoke(cli, ["kengram", "pin", "abc-123"])
    assert result.exit_code == 0
    assert "Pinned" in result.output
    assert "abc-123" in result.output
    mock_kg.fetch_entity.assert_called_once()


def test_pin_with_uuid_fallback_on_api_failure(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Pin Fallback Test"])
    with patch("bonfires.kengram.commands.kg_client") as mock_kg:
        mock_kg.fetch_entity.return_value = None
        result = runner.invoke(cli, ["kengram", "pin", "def-456"])
    assert result.exit_code == 0
    assert "Warning" in result.output
    assert "Pinned" in result.output
    assert "def-456" in result.output
    mock_kg.fetch_entity.assert_called_once()


def test_pin_with_search(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Pin Search Test"])
    fake_results = [
        {
            "uuid": "search-001",
            "name": "First Result",
            "summary": "First summary",
            "labels": ["alpha"],
        },
        {
            "uuid": "search-002",
            "name": "Second Result",
            "summary": "Second summary",
            "labels": ["beta"],
        },
    ]
    with patch("bonfires.kengram.commands.kg_client") as mock_kg:
        mock_kg.search_entities.return_value = fake_results
        result = runner.invoke(cli, ["kengram", "pin", "--search", "test query"], input="1\n")
    assert result.exit_code == 0
    assert "Pinned" in result.output
    assert "search-001" in result.output
    mock_kg.search_entities.assert_called_once()
