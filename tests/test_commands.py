"""Integration tests for kengram CLI commands using Click CliRunner."""

import json
from unittest.mock import MagicMock, patch

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


def _mock_http_response(ok=True, status_code=200, json_data=None, text=""):
    """Create a mock requests response object."""
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Original tests (Rich output)
# ---------------------------------------------------------------------------


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
    assert result.exit_code == 1
    assert "not found" in result.output


def test_kengram_export(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Export Test"])
    # Export calls _verify_for_export which calls get_entities_batch_or_none.
    # Mock the batch POST to return empty list (no entities in KG).
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": []})
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
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(json_data={"entity": fake_entity})
        result = runner.invoke(cli, ["kengram", "pin", "abc-123"])
    assert result.exit_code == 0
    assert "Pinned" in result.output
    assert "abc-123" in result.output
    mock_get.assert_called_once()


def test_pin_with_uuid_fallback_on_api_failure(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Pin Fallback Test"])
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        result = runner.invoke(cli, ["kengram", "pin", "def-456"])
    assert result.exit_code == 0
    # SDK silently returns None from get_entity_or_none on 404; pin proceeds without name
    assert "Pinned" in result.output
    assert "def-456" in result.output
    mock_get.assert_called_once()


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
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get"),
    ):
        # search uses POST /delve
        mock_post.return_value = _mock_http_response(
            json_data={"entities": fake_results}
        )
        # pin_name is set from search results, so fetch_from_kg=False — no GET call.
        result = runner.invoke(
            cli, ["kengram", "pin", "--search", "test query"], input="1\n"
        )
    assert result.exit_code == 0
    assert "Pinned" in result.output
    assert "search-001" in result.output
    mock_post.assert_called_once()


def _create_kengram_with_node(runner, tmp_path):
    """Helper: create a kEngram and pin a node with manual metadata."""
    runner.invoke(cli, ["kengram", "new", "Verify Test"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "node-001",
            "--name",
            "Alpha",
            "--summary",
            "A node",
            "--labels",
            "concept",
        ],
    )
    return runner


def test_verify_against_kg_matching(tmp_path):
    """Batch API returns entities with matching hashes — verify passes."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    fake_batch = [
        {
            "uuid": "node-001",
            "name": "Alpha",
            "summary": "A node",
            "labels": ["concept"],
        },
    ]
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": fake_batch})
        result = runner.invoke(cli, ["kengram", "verify"])
    assert result.exit_code == 0
    assert "Verified" in result.output
    assert "OK" in result.output
    mock_post.assert_called_once()


def test_verify_against_kg_drift(tmp_path):
    """Batch API returns entity with different content — per-node DRIFT shown."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    fake_batch = [
        {
            "uuid": "node-001",
            "name": "Changed Name",
            "summary": "Different",
            "labels": ["concept"],
        },
    ]
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": fake_batch})
        result = runner.invoke(cli, ["kengram", "verify"])
    assert result.exit_code == 0
    assert "DRIFT" in result.output
    mock_post.assert_called_once()


def test_verify_local_flag(tmp_path):
    """--local flag skips API call entirely."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        result = runner.invoke(cli, ["kengram", "verify", "--local"])
    assert result.exit_code == 0
    assert "Verified" in result.output
    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_verify_api_fallback(tmp_path):
    """Batch API raises error — local fallback used."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        # get_entities_batch_or_none catches APIError and returns None
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="server error"
        )
        result = runner.invoke(cli, ["kengram", "verify"])
    assert result.exit_code == 0
    # When batch returns None, verify falls through to local-only path
    assert "Verified" in result.output


def test_create_entity_success(tmp_path):
    """create command pushes entity to KG and pins it."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Create Test"])
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        # create_entity POSTs to /knowledge_graph/entity, returns uuid
        mock_post.return_value = _mock_http_response(json_data={"uuid": "new-uuid-123"})
        # After create, pin fetches entity from KG via GET
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "new-uuid-123",
                    "name": "My Entity",
                    "summary": "A test entity",
                    "labels": ["Concept", "Test"],
                }
            }
        )
        result = runner.invoke(
            cli,
            [
                "kengram",
                "create",
                "My Entity",
                "--labels",
                "Concept,Test",
                "--summary",
                "A test entity",
            ],
        )
    assert result.exit_code == 0
    assert "Created + Pinned" in result.output
    assert "new-uuid-123" in result.output
    assert "My Entity" in result.output
    mock_post.assert_called_once()


def test_create_entity_api_failure(tmp_path):
    """create command aborts when API returns error."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Create Fail Test"])
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        # API returns 500 — create_entity raises APIError
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="internal server error"
        )
        result = runner.invoke(
            cli,
            ["kengram", "create", "Bad Entity", "--summary", "Will fail"],
        )
    assert result.exit_code == 1
    assert (
        "Failed" in result.output
        or "API" in result.output
        or "error" in result.output.lower()
    )
    mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# --json flag tests
# ---------------------------------------------------------------------------


def test_json_new(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "new", "JSON Test", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "created"
    assert data["name"] == "JSON Test"
    assert data["type"] == "session"
    assert "id" in data
    assert "group_id" in data


def test_json_new_topic(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(
        cli, ["kengram", "new", "My Topic", "--type", "topic", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "created"
    assert data["type"] == "topic"
    assert data["id"].startswith("ke-topic-")


def test_json_pin(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Pin JSON"])
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "pin-uuid-1",
                    "name": "Test Node",
                    "summary": "A node",
                    "labels": ["concept"],
                }
            }
        )
        result = runner.invoke(cli, ["kengram", "pin", "pin-uuid-1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "pinned"
    assert data["uuid"] == "pin-uuid-1"
    assert "kengram_id" in data
    assert "merkle_root" in data


def test_json_pin_search_returns_results(tmp_path):
    """--json + --search returns search_results without prompting."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Search JSON"])
    fake_results = [
        {"uuid": "s-1", "name": "Result 1", "summary": "Sum 1", "labels": ["a"]},
        {"uuid": "s-2", "name": "Result 2", "summary": "Sum 2", "labels": ["b"]},
    ]
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(
            json_data={"entities": fake_results}
        )
        result = runner.invoke(cli, ["kengram", "pin", "--search", "query", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "search_results"
    assert len(data["results"]) == 2
    assert data["results"][0]["uuid"] == "s-1"


def test_json_unpin(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Unpin JSON"])
    runner.invoke(
        cli,
        ["kengram", "pin", "u-1", "--name", "Node", "--summary", "s", "--labels", "x"],
    )
    result = runner.invoke(cli, ["kengram", "unpin", "u-1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "unpinned"
    assert data["uuid"] == "u-1"


def test_json_show(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Show JSON"])
    result = runner.invoke(cli, ["kengram", "show", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "Show JSON"
    assert "pinned_nodes" in data
    assert "merkle_root" in data
    assert "id" in data


def test_json_list_empty(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kengrams"] == []


def test_json_list_with_items(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Alpha"])
    runner.invoke(cli, ["kengram", "new", "Beta"])
    result = runner.invoke(cli, ["kengram", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["kengrams"]) == 2
    names = [k["name"] for k in data["kengrams"]]
    assert "Alpha" in names
    assert "Beta" in names


def test_json_summary(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Sum JSON"])
    result = runner.invoke(cli, ["kengram", "summary", "New summary", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "updated"
    assert "id" in data


def test_json_use(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Use JSON"])
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    kengram_id = manifests[0].stem
    result = runner.invoke(cli, ["kengram", "use", kengram_id, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "active"
    assert data["id"] == kengram_id
    assert data["name"] == "Use JSON"


def test_json_delete(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Del JSON"])
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    kengram_id = manifests[0].stem
    result = runner.invoke(cli, ["kengram", "delete", kengram_id, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "deleted"
    assert data["id"] == kengram_id


def test_json_export(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Export JSON"])
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": []})
        result = runner.invoke(cli, ["kengram", "export", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "exported"
    assert "id" in data
    assert "path" in data


def test_json_verify_local(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        result = runner.invoke(cli, ["kengram", "verify", "--local", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "verified"
    assert "merkle_root" in data
    assert "nodes" in data
    assert "node-001" in data["nodes"]
    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_json_verify_kg_match(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    fake_batch = [
        {
            "uuid": "node-001",
            "name": "Alpha",
            "summary": "A node",
            "labels": ["concept"],
        },
    ]
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": fake_batch})
        result = runner.invoke(cli, ["kengram", "verify", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "verified"
    assert data["nodes"]["node-001"]["status"] == "ok"


def test_json_verify_kg_drift(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    _create_kengram_with_node(runner, tmp_path)
    fake_batch = [
        {
            "uuid": "node-001",
            "name": "Changed",
            "summary": "Different",
            "labels": ["concept"],
        },
    ]
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"entities": fake_batch})
        result = runner.invoke(cli, ["kengram", "verify", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "drift"
    assert data["nodes"]["node-001"]["status"] == "drift"
    assert "stored_hash" in data["nodes"]["node-001"]
    assert "kg_hash" in data["nodes"]["node-001"]


def test_json_create(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Create JSON"])
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        mock_post.return_value = _mock_http_response(
            json_data={"uuid": "created-uuid-1"}
        )
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "created-uuid-1",
                    "name": "New Entity",
                    "summary": "Test",
                    "labels": ["Concept"],
                }
            }
        )
        result = runner.invoke(
            cli,
            [
                "kengram",
                "create",
                "New Entity",
                "--labels",
                "Concept",
                "--summary",
                "Test",
                "--json",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "created_and_pinned"
    assert data["uuid"] == "created-uuid-1"
    assert data["name"] == "New Entity"
    assert "merkle_root" in data


def test_json_merge(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Source KG"])
    # Pin a node to source so merge has something to do
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "m-1",
            "--name",
            "MergeNode",
            "--summary",
            "s",
            "--labels",
            "x",
        ],
    )
    source_manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    source_id = source_manifests[0].stem
    runner.invoke(cli, ["kengram", "new", "Target KG", "--type", "topic"])
    target_manifests = list(
        (tmp_path / "kengrams" / "manifests").glob("ke-topic-*.json")
    )
    target_id = target_manifests[0].stem
    result = runner.invoke(
        cli, ["kengram", "merge", source_id, "--into", target_id, "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "merged"
    assert data["source"] == source_id
    assert data["target"] == target_id
    assert data["nodes"] >= 1
    assert "merkle_root" in data


def test_json_edge(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Edge JSON"])
    runner.invoke(
        cli,
        ["kengram", "pin", "e-1", "--name", "A", "--summary", "s", "--labels", "x"],
    )
    runner.invoke(
        cli,
        ["kengram", "pin", "e-2", "--name", "B", "--summary", "s", "--labels", "x"],
    )
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(json_data={"status": "ok"})
        result = runner.invoke(
            cli, ["kengram", "edge", "e-1", "e-2", "--name", "USES", "--json"]
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "edge_created"
    assert data["source"] == "e-1"
    assert data["target"] == "e-2"
    assert data["name"] == "USES"
    assert data["kg_synced"] is True
    assert "merkle_root" in data


# ---------------------------------------------------------------------------
# --json error cases
# ---------------------------------------------------------------------------


def test_json_error_no_active(tmp_path):
    """Commands that require an active kEngram should return JSON error."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "show", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data


def test_json_error_use_not_found(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "use", "ke-nonexistent", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data
    assert "not found" in data["error"]


def test_json_error_create_api_failure(tmp_path):
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Fail JSON"])
    with patch("bonfires.sdk.http.requests.post") as mock_post:
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="internal server error"
        )
        result = runner.invoke(
            cli,
            ["kengram", "create", "Bad", "--json"],
        )
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data


# ---------------------------------------------------------------------------
# repin command tests
# ---------------------------------------------------------------------------


def test_repin_success(tmp_path):
    """repin fetches fresh data from KG and updates the manifest."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin Test"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "rp-1",
            "--name",
            "OldName",
            "--summary",
            "old",
            "--labels",
            "x",
        ],
    )
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "rp-1",
                    "name": "NewName",
                    "summary": "new summary",
                    "labels": ["x", "y"],
                }
            }
        )
        result = runner.invoke(cli, ["kengram", "repin", "rp-1"])
    assert result.exit_code == 0
    assert "Repinned" in result.output
    assert "hash updated" in result.output


def test_repin_no_change(tmp_path):
    """repin with same data shows no change."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin Same"])
    runner.invoke(
        cli,
        ["kengram", "pin", "rp-2", "--name", "Same", "--summary", "s", "--labels", "a"],
    )
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "rp-2",
                    "name": "Same",
                    "summary": "s",
                    "labels": ["a"],
                }
            }
        )
        result = runner.invoke(cli, ["kengram", "repin", "rp-2"])
    assert result.exit_code == 0
    assert "no change" in result.output


def test_repin_not_pinned(tmp_path):
    """repin fails if UUID is not pinned."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin NotPinned"])
    result = runner.invoke(cli, ["kengram", "repin", "not-pinned-uuid"])
    assert result.exit_code == 1
    assert "not pinned" in result.output


def test_repin_api_failure(tmp_path):
    """repin fails gracefully when KG API is unreachable."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin API Fail"])
    runner.invoke(
        cli,
        ["kengram", "pin", "rp-3", "--name", "N", "--summary", "s", "--labels", "x"],
    )
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        result = runner.invoke(cli, ["kengram", "repin", "rp-3"])
    assert result.exit_code == 1
    assert "Could not fetch" in result.output


def test_repin_json_success(tmp_path):
    """repin --json outputs structured JSON."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin JSON"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "rp-4",
            "--name",
            "Old",
            "--summary",
            "old",
            "--labels",
            "x",
        ],
    )
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "rp-4",
                    "name": "New",
                    "summary": "new",
                    "labels": ["x"],
                }
            }
        )
        result = runner.invoke(cli, ["kengram", "repin", "rp-4", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "repinned"
    assert data["uuid"] == "rp-4"
    assert data["changed"] is True
    assert "merkle_root" in data


def test_repin_json_not_pinned(tmp_path):
    """repin --json returns error for UUID not pinned."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin JSON Err"])
    result = runner.invoke(cli, ["kengram", "repin", "not-here", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data
    assert "not pinned" in data["error"]


def test_repin_json_api_failure(tmp_path):
    """repin --json returns error when KG API fails."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Repin JSON API"])
    runner.invoke(
        cli,
        ["kengram", "pin", "rp-5", "--name", "N", "--summary", "s", "--labels", "x"],
    )
    with patch("bonfires.sdk.http.requests.get") as mock_get:
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        result = runner.invoke(cli, ["kengram", "repin", "rp-5", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data


# ---------------------------------------------------------------------------
# batch command tests
# ---------------------------------------------------------------------------


def test_batch_basic(tmp_path):
    """batch command adds nodes and edges from changeset JSON."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch Test"])
    changeset = json.dumps(
        {
            "nodes": [
                {
                    "uuid": "auto",
                    "name": "Alpha",
                    "summary": "First node",
                    "labels": ["Entity"],
                },
                {
                    "uuid": "auto",
                    "name": "Beta",
                    "summary": "Second node",
                    "labels": ["Entity"],
                },
            ],
            "edges": [
                {
                    "source": "Alpha",
                    "target": "Beta",
                    "name": "USES",
                    "fact": "Alpha uses Beta",
                },
            ],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch"], input=changeset)
    assert result.exit_code == 0
    assert "2" in result.output  # 2 nodes
    assert "1" in result.output  # 1 edge


def test_batch_json_output(tmp_path):
    """batch --json returns structured output with generated UUIDs."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch JSON"])
    changeset = json.dumps(
        {
            "nodes": [
                {
                    "uuid": "auto",
                    "name": "Gamma",
                    "summary": "A node",
                    "labels": ["Entity"],
                },
            ],
            "edges": [],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch", "--json"], input=changeset)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "batch_applied"
    assert data["nodes_added"] == 1
    assert data["edges_added"] == 0
    assert "Gamma" in data["generated_uuids"]
    assert "merkle_root" in data


def test_batch_name_resolution_existing(tmp_path):
    """batch resolves edge targets against existing manifest nodes."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch Resolve"])
    # Pin an existing node first
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "existing-uuid",
            "--name",
            "Existing",
            "--summary",
            "s",
            "--labels",
            "Entity",
        ],
    )
    changeset = json.dumps(
        {
            "nodes": [
                {
                    "uuid": "auto",
                    "name": "NewNode",
                    "summary": "New",
                    "labels": ["Entity"],
                },
            ],
            "edges": [
                {
                    "source": "NewNode",
                    "target": "Existing",
                    "name": "DEPENDS_ON",
                    "fact": "dep",
                },
            ],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch", "--json"], input=changeset)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["edges_added"] == 1


def test_batch_uuid_passthrough(tmp_path):
    """batch passes through explicit UUIDs (non-auto)."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch UUID"])
    changeset = json.dumps(
        {
            "nodes": [
                {
                    "uuid": "my-explicit-uuid",
                    "name": "Explicit",
                    "summary": "s",
                    "labels": ["Entity"],
                },
            ],
            "edges": [],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch", "--json"], input=changeset)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["nodes_added"] == 1
    # explicit uuid should not appear in generated_uuids
    assert "Explicit" not in data["generated_uuids"]


def test_batch_unresolvable_edge(tmp_path):
    """batch errors when edge references an unresolvable name."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch Err"])
    changeset = json.dumps(
        {
            "nodes": [],
            "edges": [
                {
                    "source": "NonExistent",
                    "target": "AlsoNot",
                    "name": "REL",
                    "fact": "",
                },
            ],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch", "--json"], input=changeset)
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data


def test_batch_with_canvas(tmp_path):
    """batch --canvas regenerates the canvas file."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch Canvas"])
    changeset = json.dumps(
        {
            "nodes": [
                {
                    "uuid": "auto",
                    "name": "CanvasNode",
                    "summary": "s",
                    "labels": ["Entity"],
                },
            ],
            "edges": [],
        }
    )
    result = runner.invoke(cli, ["kengram", "batch", "--canvas"], input=changeset)
    assert result.exit_code == 0
    canvas_files = list((tmp_path / "kengrams" / "canvas").glob("*.canvas"))
    assert len(canvas_files) == 1


def test_batch_from_file(tmp_path):
    """batch reads changeset from a file argument."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Batch File"])
    changeset_file = tmp_path / "changeset.json"
    changeset_file.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "uuid": "auto",
                        "name": "FileNode",
                        "summary": "from file",
                        "labels": ["Entity"],
                    },
                ],
                "edges": [],
            }
        )
    )
    result = runner.invoke(cli, ["kengram", "batch", str(changeset_file), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["nodes_added"] == 1


# ---------------------------------------------------------------------------
# push command tests
# ---------------------------------------------------------------------------


def test_push_nodes_not_in_kg(tmp_path):
    """push creates nodes that don't exist in KG and skips those that do."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Nodes"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "p-new",
            "--name",
            "NewNode",
            "--summary",
            "A new node",
            "--labels",
            "Entity",
        ],
    )
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "p-exists",
            "--name",
            "ExistingNode",
            "--summary",
            "Already in KG",
            "--labels",
            "Entity",
        ],
    )
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):

        def get_side_effect(url, **kwargs):
            # get_entity_or_none calls GET /knowledge_graph/entity/{uuid}
            if "p-exists" in url:
                return _mock_http_response(
                    json_data={
                        "entity": {
                            "uuid": "p-exists",
                            "name": "ExistingNode",
                            "summary": "Already in KG",
                            "labels": ["Entity"],
                        }
                    }
                )
            # p-new not in KG
            return _mock_http_response(ok=False, status_code=404, text="not found")

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            if "/entity" in url and "/update" not in url:
                return _mock_http_response(json_data={"uuid": "p-new"})
            if "/edge" in url:
                return _mock_http_response(json_data={"status": "ok"})
            return _mock_http_response(json_data={})

        mock_post.side_effect = post_side_effect
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    assert "Pushed" in result.output


def test_push_all_nodes_exist(tmp_path):
    """push skips all nodes when they already exist in KG."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push All Exist"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "pe-1",
            "--name",
            "Exists1",
            "--summary",
            "s",
            "--labels",
            "Entity",
        ],
    )
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "pe-1",
                    "name": "Exists1",
                    "summary": "s",
                    "labels": ["Entity"],
                }
            }
        )
        mock_post.return_value = _mock_http_response(json_data={"status": "ok"})
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    assert "Pushed" in result.output


def test_push_edges(tmp_path):
    """push sends edges to KG."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Edges"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "pe-src",
            "--name",
            "Src",
            "--summary",
            "s",
            "--labels",
            "Entity",
        ],
    )
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "pe-tgt",
            "--name",
            "Tgt",
            "--summary",
            "t",
            "--labels",
            "Entity",
        ],
    )
    # First add edge locally
    runner.invoke(
        cli, ["kengram", "edge", "pe-src", "pe-tgt", "--name", "USES", "--local"]
    )
    # Now push — all nodes exist in KG, edge gets pushed
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "pe-src",
                    "name": "Src",
                    "summary": "s",
                    "labels": ["Entity"],
                }
            }
        )
        mock_post.return_value = _mock_http_response(json_data={"status": "ok"})
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    # At least one edge POST call should have been made
    assert mock_post.call_count >= 1


def test_push_repins_pushed_nodes(tmp_path):
    """push re-fetches canonical data and updates hashes for pushed nodes."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Repin"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "rp-push",
            "--name",
            "Local",
            "--summary",
            "local-sum",
            "--labels",
            "Entity",
        ],
    )
    canonical = {
        "uuid": "rp-push",
        "name": "Canonical",
        "summary": "canonical-sum",
        "labels": ["Entity", "Extra"],
    }
    get_call_count = 0
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):

        def get_side_effect(url, **kwargs):
            nonlocal get_call_count
            get_call_count += 1
            if get_call_count == 1:
                # First call: existence check — not in KG
                return _mock_http_response(ok=False, status_code=404, text="not found")
            # Second call: re-fetch after push — returns canonical
            return _mock_http_response(json_data={"entity": canonical})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            if "/entity" in url and "/update" not in url:
                return _mock_http_response(json_data={"uuid": "rp-push"})
            if "/edge" in url:
                return _mock_http_response(json_data={"status": "ok"})
            return _mock_http_response(json_data={})

        mock_post.side_effect = post_side_effect
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    # Verify the manifest was updated with canonical data
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    assert len(manifests) == 1
    import json as _json

    data = _json.loads(manifests[0].read_text())
    assert data["node_meta"]["rp-push"]["name"] == "Canonical"


def test_push_create_entity_returns_none(tmp_path):
    """push counts node as skipped when create_entity raises APIError."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Create Fail"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "cf-1",
            "--name",
            "FailNode",
            "--summary",
            "will fail",
            "--labels",
            "Entity",
        ],
    )
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        # Node not in KG
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        # create_entity fails (no uuid in response) — SDK raises APIError, push catches it
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="internal server error"
        )
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    assert "Pushed" in result.output
    # Output should show 0 pushed
    assert "0" in result.output


def test_push_repins_with_different_canonical_uuid(tmp_path):
    """push migrates manifest entries when server returns a different canonical UUID."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push UUID Remap"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "local-uuid-1",
            "--name",
            "MyNode",
            "--summary",
            "desc",
            "--labels",
            "Entity",
        ],
    )
    canonical = {
        "uuid": "server-uuid-1",
        "name": "MyNode",
        "summary": "desc",
        "labels": ["Entity"],
    }
    get_call_count = 0
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):

        def get_side_effect(url, **kwargs):
            nonlocal get_call_count
            get_call_count += 1
            if get_call_count == 1:
                # First call: existence check — not in KG
                return _mock_http_response(ok=False, status_code=404, text="not found")
            # Second call: re-fetch with canonical UUID
            return _mock_http_response(json_data={"entity": canonical})

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            if "/entity" in url and "/update" not in url:
                return _mock_http_response(json_data={"uuid": "server-uuid-1"})
            if "/edge" in url:
                return _mock_http_response(json_data={"status": "ok"})
            return _mock_http_response(json_data={})

        mock_post.side_effect = post_side_effect
        result = runner.invoke(cli, ["kengram", "push"])
    assert result.exit_code == 0
    # Manifest should now use server-uuid-1, not local-uuid-1
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    assert len(manifests) == 1
    import json as _json

    data = _json.loads(manifests[0].read_text())
    assert "server-uuid-1" in data["node_meta"]
    assert "local-uuid-1" not in data["node_meta"]
    assert "server-uuid-1" in data.get("pinned_nodes", [])
    assert "local-uuid-1" not in data.get("pinned_nodes", [])


def test_push_with_id_option(tmp_path):
    """push --id targets a specific kEngram."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push By ID"])
    manifests = list((tmp_path / "kengrams" / "manifests").glob("ke-*.json"))
    kengram_id = manifests[0].stem
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        mock_post.return_value = _mock_http_response(json_data={})
        result = runner.invoke(cli, ["kengram", "push", "--id", kengram_id])
    assert result.exit_code == 0
    assert "Pushed" in result.output


def test_push_id_not_found(tmp_path):
    """push --id with unknown ID shows error."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "push", "--id", "ke-nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_json_push(tmp_path):
    """push --json returns structured counts."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push JSON"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "pj-1",
            "--name",
            "Node1",
            "--summary",
            "s",
            "--labels",
            "Entity",
        ],
    )
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "pj-2",
            "--name",
            "Node2",
            "--summary",
            "s",
            "--labels",
            "Entity",
        ],
    )
    # Add edge locally
    runner.invoke(
        cli, ["kengram", "edge", "pj-1", "pj-2", "--name", "LINKS", "--local"]
    )

    canonical_node = {
        "uuid": "pj-1",
        "name": "Node1",
        "summary": "s",
        "labels": ["Entity"],
    }
    create_entity_called = False
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):

        def get_side_effect(url, **kwargs):
            nonlocal create_entity_called
            if "pj-2" in url:
                return _mock_http_response(
                    json_data={
                        "entity": {
                            "uuid": "pj-2",
                            "name": "Node2",
                            "summary": "s",
                            "labels": ["Entity"],
                        }
                    }
                )
            if create_entity_called:
                return _mock_http_response(json_data={"entity": canonical_node})
            return _mock_http_response(ok=False, status_code=404, text="not found")

        mock_get.side_effect = get_side_effect

        def post_side_effect(url, **kwargs):
            nonlocal create_entity_called
            if "/entity" in url and "/update" not in url:
                create_entity_called = True
                return _mock_http_response(json_data={"uuid": "pj-1"})
            if "/edge" in url:
                return _mock_http_response(json_data={"status": "ok"})
            return _mock_http_response(json_data={})

        mock_post.side_effect = post_side_effect
        result = runner.invoke(cli, ["kengram", "push", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "pushed"
    assert "kengram_id" in data
    assert "nodes_pushed" in data
    assert "nodes_skipped" in data
    assert "edges_pushed" in data
    assert "edges_skipped" in data
    assert "merkle_root" in data
    assert data["nodes_pushed"] == 1
    assert data["nodes_skipped"] == 1
    assert data["edges_pushed"] == 1


def test_json_push_no_active(tmp_path):
    """push --json returns error when no active kEngram."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    result = runner.invoke(cli, ["kengram", "push", "--json"])
    assert result.exit_code != 0
    data = json.loads(result.output)
    assert "error" in data


# ---------------------------------------------------------------------------
# push --changes tests
# ---------------------------------------------------------------------------


def test_push_with_changes_updates_dirty_nodes(tmp_path):
    """push --changes updates dirty nodes and creates new ones."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Changes"])
    runner.invoke(
        cli,
        [
            "kengram",
            "pin",
            "dirty-1",
            "--name",
            "OldName",
            "--summary",
            "old",
            "--labels",
            "Entity",
        ],
    )
    changes = json.dumps(
        {
            "dirty": {
                "dirty-1": {
                    "name": "NewName",
                    "summary": "updated",
                    "labels": ["Entity", "Modified"],
                }
            },
            "new_nodes": {
                "canvas-new-1": {
                    "name": "BrandNew",
                    "summary": "fresh",
                    "labels": ["Concept"],
                }
            },
            "new_edges": [
                {"from": "dirty-1", "to": "canvas-new-1", "label": "RELATES_TO"}
            ],
        }
    )
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        # All existing nodes are "in KG" for push (skipped for creation)
        mock_get.return_value = _mock_http_response(
            json_data={
                "entity": {
                    "uuid": "dirty-1",
                    "name": "OldName",
                    "summary": "old",
                    "labels": ["Entity"],
                }
            }
        )

        def post_side_effect(url, **kwargs):
            if "/entity/" in url and "/update" in url:
                return _mock_http_response(
                    json_data={"success": True, "uuid": "dirty-1"}
                )
            if "/entity" in url:
                return _mock_http_response(json_data={"uuid": "new-uuid-1"})
            if "/edge" in url:
                return _mock_http_response(json_data={"status": "ok"})
            return _mock_http_response(json_data={})

        mock_post.side_effect = post_side_effect
        result = runner.invoke(cli, ["kengram", "push", "--changes", changes, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["nodes_updated"] == 1
    assert data["nodes_created"] == 1
    assert data["edges_created"] == 1


def test_push_with_changes_invalid_json(tmp_path):
    """push --changes with invalid JSON silently skips canvas changes."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push Bad Changes"])
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="error"
        )
        result = runner.invoke(
            cli, ["kengram", "push", "--changes", "not-valid-json", "--json"]
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["nodes_updated"] == 0
    assert data["nodes_created"] == 0
    assert data["edges_created"] == 0


def test_push_with_changes_no_changes_flag(tmp_path):
    """push without --changes sets updated/created/edges_created to 0 in JSON output."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Push No Changes"])
    with (
        patch("bonfires.sdk.http.requests.get") as mock_get,
        patch("bonfires.sdk.http.requests.post") as mock_post,
    ):
        mock_get.return_value = _mock_http_response(
            ok=False, status_code=404, text="not found"
        )
        mock_post.return_value = _mock_http_response(
            ok=False, status_code=500, text="error"
        )
        result = runner.invoke(cli, ["kengram", "push", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["nodes_updated"] == 0
    assert data["nodes_created"] == 0
    assert data["edges_created"] == 0


# ---------------------------------------------------------------------------
# edge --local tests
# ---------------------------------------------------------------------------


def test_edge_local_skips_kg(tmp_path):
    """edge --local skips KG sync."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Edge Local"])
    runner.invoke(
        cli,
        ["kengram", "pin", "el-1", "--name", "A", "--summary", "s", "--labels", "x"],
    )
    runner.invoke(
        cli,
        ["kengram", "pin", "el-2", "--name", "B", "--summary", "s", "--labels", "x"],
    )
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        result = runner.invoke(
            cli, ["kengram", "edge", "el-1", "el-2", "--name", "USES", "--local"]
        )
    assert result.exit_code == 0
    assert "Edge" in result.output
    mock_post.assert_not_called()
    mock_get.assert_not_called()


def test_edge_local_json(tmp_path):
    """edge --local --json returns structured output with kg_synced=false."""
    runner = CliRunner(env=_env_overrides(tmp_path))
    runner.invoke(cli, ["kengram", "new", "Edge Local JSON"])
    runner.invoke(
        cli,
        ["kengram", "pin", "elj-1", "--name", "A", "--summary", "s", "--labels", "x"],
    )
    runner.invoke(
        cli,
        ["kengram", "pin", "elj-2", "--name", "B", "--summary", "s", "--labels", "x"],
    )
    with (
        patch("bonfires.sdk.http.requests.post") as mock_post,
        patch("bonfires.sdk.http.requests.get") as mock_get,
    ):
        result = runner.invoke(
            cli,
            [
                "kengram",
                "edge",
                "elj-1",
                "elj-2",
                "--name",
                "USES",
                "--local",
                "--json",
            ],
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "edge_created"
    assert data["kg_synced"] is False
    mock_post.assert_not_called()
    mock_get.assert_not_called()
