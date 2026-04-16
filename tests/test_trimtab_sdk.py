"""Tests for bonfires.sdk.trimtab.TrimtabService — new methods added in Task 11."""

from unittest.mock import MagicMock, patch

import pytest

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.trimtab import TrimtabService


@pytest.fixture()
def cfg(tmp_path):
    return BonfiresConfig(
        api_key="test-key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir=str(tmp_path),
    )


@pytest.fixture()
def svc(cfg):
    return TrimtabService(cfg)


def _ok(payload: dict):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = payload
    return mock_resp


# === update ===


@patch("bonfires.sdk.http.requests.post")
def test_update_text(mock_post, svc):
    mock_post.return_value = _ok({"grammar": "notes", "id": "exp-1", "text": "new text", "metadata": {}})
    result = svc.update("notes", "exp-1", text="new text")
    assert result["id"] == "exp-1"
    assert result["text"] == "new text"
    body = mock_post.call_args.kwargs["json"]
    assert body["grammar"] == "notes"
    assert body["id"] == "exp-1"
    assert body["text"] == "new text"
    assert body["metadata"] is None


@patch("bonfires.sdk.http.requests.post")
def test_update_metadata_only(mock_post, svc):
    meta = {"source": "kg"}
    mock_post.return_value = _ok({"grammar": "notes", "id": "exp-2", "text": "old", "metadata": meta})
    result = svc.update("notes", "exp-2", metadata=meta)
    assert result["metadata"] == meta
    body = mock_post.call_args.kwargs["json"]
    assert body["text"] is None
    assert body["metadata"] == meta


# === remove ===


@patch("bonfires.sdk.http.requests.post")
def test_remove(mock_post, svc):
    mock_post.return_value = _ok({"grammar": "notes", "id": "exp-3", "deleted": True})
    result = svc.remove("notes", "exp-3")
    assert result["deleted"] is True
    body = mock_post.call_args.kwargs["json"]
    assert body["grammar"] == "notes"
    assert body["id"] == "exp-3"


# === list_expansions ===


@patch("bonfires.sdk.http.requests.post")
def test_list_expansions_minimal(mock_post, svc):
    mock_post.return_value = _ok({"grammar": "notes", "expansions": [], "total": 0})
    result = svc.list_expansions("notes")
    assert result["total"] == 0
    body = mock_post.call_args.kwargs["json"]
    assert body["grammar"] == "notes"
    assert body["rule"] is None
    assert body["filter_metadata"] is None
    assert body["sort_by"] is None
    assert body["sort_desc"] is False
    assert body["limit"] is None


@patch("bonfires.sdk.http.requests.post")
def test_list_expansions_with_options(mock_post, svc):
    expansions = [{"id": "e1", "text": "foo"}]
    mock_post.return_value = _ok({"grammar": "notes", "expansions": expansions, "total": 1})
    result = svc.list_expansions(
        "notes",
        rule="main",
        filter_metadata={"source": "kg"},
        sort_by="text",
        sort_desc=True,
        limit=10,
    )
    assert result["total"] == 1
    body = mock_post.call_args.kwargs["json"]
    assert body["rule"] == "main"
    assert body["filter_metadata"] == {"source": "kg"}
    assert body["sort_by"] == "text"
    assert body["sort_desc"] is True
    assert body["limit"] == 10


# === summary ===


@patch("bonfires.sdk.http.requests.get")
def test_summary(mock_get, svc, cfg):
    mock_get.return_value = _ok({"bonfire_id": cfg.bonfire_id, "grammars": ["notes", "quests"]})
    result = svc.summary()
    assert result["bonfire_id"] == cfg.bonfire_id
    assert "notes" in result["grammars"]
    called_url = mock_get.call_args.args[0]
    assert "/trimtabs/grammars/bf-1/summary" in called_url


# === search_and_expand ===


@patch("bonfires.sdk.http.requests.post")
def test_search_and_expand(mock_post, svc):
    payload = {
        "text": "expanded text",
        "center_ids": ["uuid-1"],
        "kg_contexts": {"uuid-1": {"neighbors": []}},
    }
    mock_post.return_value = _ok(payload)
    result = svc.search_and_expand("notes", "find my goals", top_k=5)
    assert result["text"] == "expanded text"
    assert "uuid-1" in result["center_ids"]
    body = mock_post.call_args.kwargs["json"]
    assert body["grammar"] == "notes"
    assert body["query"] == "find my goals"
    assert body["top_k"] == 5
    called_url = mock_post.call_args.args[0]
    assert "/trimtabs/grammars/bf-1/search-and-expand" in called_url


@patch("bonfires.sdk.http.requests.post")
def test_search_and_expand_default_top_k(mock_post, svc):
    mock_post.return_value = _ok({"text": "", "center_ids": [], "kg_contexts": {}})
    svc.search_and_expand("notes", "query")
    body = mock_post.call_args.kwargs["json"]
    assert body["top_k"] == 3


# === lens_search ===


@patch("bonfires.sdk.http.requests.post")
def test_lens_search_default_grammars(mock_post, svc):
    payload = {"quests": {}, "notes": {}, "friends": {}, "tasks": {}}
    mock_post.return_value = _ok(payload)
    result = svc.lens_search("what do I know about alice?")
    assert "quests" in result
    body = mock_post.call_args.kwargs["json"]
    assert body["query"] == "what do I know about alice?"
    assert body["top_k"] == 3
    assert "grammars" not in body  # not sent when None
    called_url = mock_post.call_args.args[0]
    assert "/trimtabs/grammars/bf-1/lens-search" in called_url


@patch("bonfires.sdk.http.requests.post")
def test_lens_search_explicit_grammars(mock_post, svc):
    mock_post.return_value = _ok({"notes": {}, "quests": {}})
    svc.lens_search("find context", grammars=["notes", "quests"], top_k=5)
    body = mock_post.call_args.kwargs["json"]
    assert body["grammars"] == ["notes", "quests"]
    assert body["top_k"] == 5
