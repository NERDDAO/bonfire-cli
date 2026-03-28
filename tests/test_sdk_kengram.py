"""Tests for bonfires.sdk.kengram.KEngramService."""

from unittest.mock import MagicMock

import pytest

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import NotFoundError
from bonfires.sdk.kengram import KEngramService


@pytest.fixture()
def cfg(tmp_path):
    return BonfiresConfig(
        api_key="test-key",
        bonfire_id="bf-1",
        agent_id="ag-1",
        vault_dir=str(tmp_path),
    )


@pytest.fixture()
def mock_kg():
    kg = MagicMock()
    kg.get_entity_or_none.return_value = {
        "uuid": "entity-1",
        "name": "Test Entity",
        "summary": "A test",
        "labels": ["concept"],
    }
    kg.get_entities_batch_or_none.return_value = None
    return kg


@pytest.fixture()
def svc(cfg, mock_kg):
    return KEngramService(cfg, mock_kg)


def test_create(svc):
    manifest = svc.create("test-kengram")
    assert manifest.name == "test-kengram"
    assert manifest.kengram_type == "session"
    assert svc.get_active_id() is not None


def test_create_topic(svc):
    manifest = svc.create("my-topic", type="topic")
    assert manifest.kengram_type == "topic"
    assert manifest.id.startswith("ke-topic-")


def test_get(svc):
    created = svc.create("test-get")
    loaded = svc.get(created.id)
    assert loaded.id == created.id
    assert loaded.name == "test-get"


def test_get_not_found(svc):
    with pytest.raises(NotFoundError, match="not found"):
        svc.get("ke-nonexistent")


def test_get_active(svc):
    created = svc.create("active-test")
    active = svc.get_active()
    assert active.id == created.id


def test_get_active_none_set(svc):
    with pytest.raises(NotFoundError, match="No active"):
        svc.get_active()


def test_list_empty(svc):
    assert svc.list() == []


def test_list(svc):
    svc.create("a")
    svc.create("b")
    items = svc.list()
    assert len(items) == 2


def test_delete(svc):
    manifest = svc.create("to-delete")
    assert svc.delete(manifest.id) is True
    assert svc.delete(manifest.id) is False


def test_set_active(svc):
    m1 = svc.create("first")
    svc.create("second")
    svc.set_active(m1.id)
    assert svc.get_active().id == m1.id


def test_set_active_not_found(svc):
    with pytest.raises(NotFoundError):
        svc.set_active("ke-missing")


def test_update_summary(svc):
    manifest = svc.create("summary-test")
    updated = svc.update_summary(manifest.id, "new summary")
    assert updated.summary == "new summary"


def test_pin(svc):
    manifest = svc.create("pin-test")
    result = svc.pin(manifest.id, "entity-1")
    assert "entity-1" in result["manifest"].pinned_nodes
    assert result["manifest"]._node_meta["entity-1"]["name"] == "Test Entity"


def test_pin_with_explicit_metadata(svc, mock_kg):
    manifest = svc.create("pin-explicit")
    result = svc.pin(
        manifest.id,
        "entity-2",
        name="Manual",
        summary="Manually set",
        labels=["custom"],
        fetch_from_kg=False,
    )
    assert result["manifest"]._node_meta["entity-2"]["name"] == "Manual"
    mock_kg.get_entity_or_none.assert_not_called()


def test_unpin(svc):
    manifest = svc.create("unpin-test")
    svc.pin(manifest.id, "entity-1")
    result = svc.unpin(manifest.id, "entity-1")
    assert "entity-1" not in result.pinned_nodes


def test_add_edge(svc):
    manifest = svc.create("edge-test")
    svc.pin(manifest.id, "entity-1", name="A", fetch_from_kg=False)
    svc.pin(manifest.id, "entity-2", name="B", fetch_from_kg=False)
    result = svc.add_edge(
        manifest.id, "entity-1", "entity-2", "RELATES_TO", sync_to_kg=False
    )
    assert len(result["manifest"].pinned_edges) == 1
    assert result["kg_synced"] is False


def test_add_edge_source_not_pinned(svc):
    manifest = svc.create("edge-fail")
    svc.pin(manifest.id, "entity-1", name="A", fetch_from_kg=False)
    with pytest.raises(NotFoundError, match="not pinned"):
        svc.add_edge(manifest.id, "missing", "entity-1", "REL")


def test_batch(svc):
    manifest = svc.create("batch-test")
    changeset = {
        "nodes": [
            {"name": "Node A", "summary": "First", "labels": ["concept"]},
            {"name": "Node B", "summary": "Second", "labels": ["concept"]},
        ],
        "edges": [
            {"source": "Node A", "target": "Node B", "name": "RELATES_TO"},
        ],
    }
    result = svc.batch(manifest.id, changeset)
    assert result["nodes_added"] == 2
    assert result["edges_added"] == 1
    assert "Node A" in result["generated_uuids"]
    assert "Node B" in result["generated_uuids"]


def test_merge(svc):
    target = svc.create("target")
    svc.pin(target.id, "entity-1", name="A", fetch_from_kg=False)

    source = svc.create("source")
    svc.pin(source.id, "entity-2", name="B", fetch_from_kg=False)

    merged = svc.merge(target.id, source.id)
    assert "entity-1" in merged.pinned_nodes
    assert "entity-2" in merged.pinned_nodes


def test_verify_local(svc):
    manifest = svc.create("verify-test")
    svc.pin(
        manifest.id,
        "entity-1",
        name="A",
        summary="s",
        labels=["l"],
        fetch_from_kg=False,
    )

    result = svc.verify(manifest.id, local_only=True)
    assert result["status"] == "verified"
    assert result["nodes"]["entity-1"]["status"] == "local_only"


def test_export_canvas(svc):
    manifest = svc.create("export-test")
    svc.pin(manifest.id, "e1", name="A", summary="s", labels=["l"], fetch_from_kg=False)

    path = svc.export(manifest.id, format="canvas")
    assert path.endswith(".canvas")


def test_repin(svc, mock_kg):
    manifest = svc.create("repin-test")
    svc.pin(manifest.id, "entity-1", name="Old Name", fetch_from_kg=False)

    mock_kg.get_entity_or_none.return_value = {
        "uuid": "entity-1",
        "name": "New Name",
        "summary": "Updated",
        "labels": ["updated"],
    }
    result = svc.repin(manifest.id, "entity-1")
    assert result["changed"] is True

    loaded = svc.get(manifest.id)
    assert loaded._node_meta["entity-1"]["name"] == "New Name"


def test_repin_not_pinned(svc):
    manifest = svc.create("repin-fail")
    with pytest.raises(NotFoundError, match="not pinned"):
        svc.repin(manifest.id, "not-pinned-uuid")
