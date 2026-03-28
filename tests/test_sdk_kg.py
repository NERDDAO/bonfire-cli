"""Tests for bonfires.sdk.kg.KGService."""

from unittest.mock import MagicMock, patch

import pytest

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import APIError, NotFoundError
from bonfires.sdk.kg import KGService


@pytest.fixture()
def cfg(tmp_path):
    return BonfiresConfig(
        api_key="test-key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir=str(tmp_path),
    )


@pytest.fixture()
def kg(cfg):
    return KGService(cfg)


@patch("bonfires.sdk.http.requests.post")
def test_search(mock_post, kg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "entities": [{"uuid": "u1", "name": "A"}],
        "query": "test",
    }
    mock_post.return_value = mock_resp

    result = kg.search("test", num_results=5)
    assert "entities" in result
    assert result["entities"][0]["name"] == "A"


@patch("bonfires.sdk.http.requests.get")
def test_get_entity(mock_get, kg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"entity": {"uuid": "u1", "name": "Entity A"}}
    mock_get.return_value = mock_resp

    entity = kg.get_entity("u1")
    assert entity["name"] == "Entity A"


@patch("bonfires.sdk.http.requests.get")
def test_get_entity_not_found(mock_get, kg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_get.return_value = mock_resp

    with pytest.raises(NotFoundError):
        kg.get_entity("missing-uuid")


@patch("bonfires.sdk.http.requests.get")
def test_get_entity_or_none(mock_get, kg):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_get.return_value = mock_resp

    assert kg.get_entity_or_none("missing") is None


@patch("bonfires.sdk.http.requests.post")
def test_create_entity(mock_post, kg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"uuid": "new-uuid-123"}
    mock_post.return_value = mock_resp

    uuid = kg.create_entity("Test Entity", ["concept"], {"summary": "desc"})
    assert uuid == "new-uuid-123"


@patch("bonfires.sdk.http.requests.post")
def test_create_entity_no_uuid_raises(mock_post, kg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"status": "ok"}
    mock_post.return_value = mock_resp

    with pytest.raises(APIError, match="No UUID"):
        kg.create_entity("Test", ["label"], {})


@patch("bonfires.sdk.http.requests.post")
def test_create_edge(mock_post, kg):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"status": "created"}
    mock_post.return_value = mock_resp

    result = kg.create_edge("src-uuid", "tgt-uuid", "RELATES_TO", "fact text")
    assert result["status"] == "created"
