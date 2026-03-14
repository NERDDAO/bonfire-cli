"""Tests for the KG API client wrapper."""

from unittest.mock import patch

from bonfires.kengram.kg_client import (
    create_edge,
    create_entity,
    fetch_entities_batch,
    fetch_entity,
    search_entities,
)

CFG = {
    "api_url": "https://api.example.com",
    "bonfire_id": "bf-123",
    "agent_id": "agent-456",
    "api_key": "test-key",
    "vault_dir": "/tmp/vault",
    "group_id": "grp-789",
}


@patch("bonfires.kengram.kg_client.api_get")
def test_fetch_entity_success(mock_get):
    mock_get.return_value = {"success": True, "entity": {"uuid": "abc", "name": "Node"}}
    result = fetch_entity(CFG, "abc")
    assert result == {"uuid": "abc", "name": "Node"}
    mock_get.assert_called_once_with(
        CFG,
        "/knowledge_graph/entity/abc",
        params={"bonfire_id": "bf-123"},
    )


@patch("bonfires.kengram.kg_client.api_get")
def test_fetch_entity_returns_none_on_failure(mock_get):
    mock_get.side_effect = SystemExit(1)
    result = fetch_entity(CFG, "abc")
    assert result is None


@patch("bonfires.kengram.kg_client.api_post")
def test_fetch_entities_batch_success(mock_post):
    entities = [{"uuid": "a"}, {"uuid": "b"}]
    mock_post.return_value = {"success": True, "entities": entities}
    result = fetch_entities_batch(CFG, ["a", "b"])
    assert result == entities
    mock_post.assert_called_once_with(
        CFG,
        "/knowledge_graph/entities/batch?bonfire_id=bf-123",
        body={"entity_uuids": ["a", "b"]},
    )


@patch("bonfires.kengram.kg_client.api_post")
def test_fetch_entities_batch_returns_none_on_failure(mock_post):
    mock_post.side_effect = SystemExit(1)
    result = fetch_entities_batch(CFG, ["a", "b"])
    assert result is None


@patch("bonfires.kengram.kg_client.api_post")
def test_search_entities_success(mock_post):
    entities = [{"uuid": "x", "name": "Found"}]
    mock_post.return_value = {"success": True, "entities": entities}
    result = search_entities(CFG, "test query", num_results=5)
    assert result == entities
    mock_post.assert_called_once_with(
        CFG,
        "/delve",
        body={
            "query": "test query",
            "bonfire_id": "bf-123",
            "num_results": 5,
            "agent_id": "agent-456",
        },
    )


@patch("bonfires.kengram.kg_client.api_post")
def test_search_entities_default_num_results(mock_post):
    mock_post.return_value = {"success": True, "entities": []}
    search_entities(CFG, "q")
    call_body = mock_post.call_args[1]["body"] if mock_post.call_args[1] else mock_post.call_args[0][2]
    assert call_body["num_results"] == 10


@patch("bonfires.kengram.kg_client.api_post")
def test_search_entities_returns_none_on_failure(mock_post):
    mock_post.side_effect = SystemExit(1)
    result = search_entities(CFG, "query")
    assert result is None


@patch("bonfires.kengram.kg_client.api_post")
def test_create_entity_success(mock_post):
    mock_post.return_value = {"uuid": "new-uuid-123"}
    result = create_entity(CFG, "TestNode", ["Label1"], {"key": "val"})
    assert result == "new-uuid-123"
    mock_post.assert_called_once_with(
        CFG,
        "/knowledge_graph/entity",
        body={
            "name": "TestNode",
            "labels": ["Label1"],
            "attributes": {"key": "val"},
            "bonfire_id": "bf-123",
        },
    )


@patch("bonfires.kengram.kg_client.api_post")
def test_create_entity_returns_none_on_failure(mock_post):
    mock_post.side_effect = SystemExit(1)
    result = create_entity(CFG, "TestNode", ["Label1"], {"key": "val"})
    assert result is None


@patch("bonfires.kengram.kg_client.api_post")
def test_create_edge_success(mock_post):
    mock_post.return_value = {"success": True, "edge_uuid": "edge-1", "source_uuid": "src-1", "target_uuid": "tgt-1"}
    result = create_edge(CFG, "src-1", "tgt-1", "USES", fact="Source uses Target")
    assert result is not None
    assert result["success"] is True
    mock_post.assert_called_once_with(
        CFG,
        "/knowledge_graph/edge",
        body={
            "bonfire_id": "bf-123",
            "source_uuid": "src-1",
            "target_uuid": "tgt-1",
            "edge_name": "USES",
            "fact": "Source uses Target",
        },
    )


@patch("bonfires.kengram.kg_client.api_post")
def test_create_edge_returns_none_on_failure(mock_post):
    mock_post.side_effect = SystemExit(1)
    result = create_edge(CFG, "src-1", "tgt-1", "USES")
    assert result is None


@patch("bonfires.kengram.kg_client.api_post")
def test_create_edge_default_fact(mock_post):
    mock_post.return_value = {"success": True}
    create_edge(CFG, "src-1", "tgt-1", "RELATES_TO")
    call_body = mock_post.call_args[0][2] if len(mock_post.call_args[0]) > 2 else mock_post.call_args[1]["body"]
    assert call_body["fact"] == ""
