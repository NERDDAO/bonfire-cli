"""Tests for kEngram manifest operations."""

import json

from bonfires.kengram.manifest import KEngramManifest


def test_create_session_manifest():
    m = KEngramManifest.create(
        name="Test Session",
        kengram_type="session",
        group_id="test-group",
    )
    assert m.name == "Test Session"
    assert m.kengram_type == "session"
    assert m.group_id == "test-group"
    assert m.id.startswith("ke-")
    assert m.pinned_nodes == []
    assert m.pinned_edges == []
    assert m.episodes == []
    assert m.merkle_root is not None
    assert m.parent_topic is None


def test_create_topic_manifest():
    m = KEngramManifest.create(name="My Topic", kengram_type="topic", group_id="g")
    assert m.kengram_type == "topic"
    assert m.id.startswith("ke-topic-")


def test_pin_node():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    old_root = m.merkle_root
    m.pin_node(uuid="abc123", name="Entity", summary="A thing", labels=["Entity"])
    assert "abc123" in m.pinned_nodes
    assert m.merkle_root != old_root


def test_pin_node_dedup():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_node(uuid="abc", name="X", summary="Y", labels=[])
    m.pin_node(uuid="abc", name="X", summary="Y", labels=[])
    assert m.pinned_nodes.count("abc") == 1


def test_unpin_node():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_node(uuid="abc", name="X", summary="Y", labels=[])
    m.unpin_node("abc")
    assert "abc" not in m.pinned_nodes


def test_pin_edge():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed")
    assert "a:b:REPAIRS" in m.pinned_edges


def test_pin_edge_dedup():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed")
    m.pin_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed")
    assert m.pinned_edges.count("a:b:REPAIRS") == 1


def test_add_episode():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.add_episode("ep1")
    m.add_episode("ep1")
    assert m.episodes == ["ep1"]


def test_update_summary():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.update_summary("New summary text")
    assert m.summary == "New summary text"


def test_merge():
    source = KEngramManifest.create(name="Session", kengram_type="session", group_id="g")
    source.pin_node(uuid="abc", name="X", summary="Y", labels=[])
    source.pin_edge(source_uuid="a", target_uuid="b", name="REL", fact="F")
    source.add_episode("ep1")

    target = KEngramManifest.create(name="Topic", kengram_type="topic", group_id="g")
    target.pin_node(uuid="def", name="Z", summary="W", labels=[])
    target.add_episode("ep2")

    target.merge(source)

    assert "abc" in target.pinned_nodes
    assert "def" in target.pinned_nodes
    assert "a:b:REL" in target.pinned_edges
    assert "ep1" in target.episodes
    assert "ep2" in target.episodes


def test_merge_idempotent():
    source = KEngramManifest.create(name="S", kengram_type="session", group_id="g")
    source.pin_node(uuid="abc", name="X", summary="Y", labels=[])

    target = KEngramManifest.create(name="T", kengram_type="topic", group_id="g")
    target.merge(source)
    root_after_first = target.merkle_root
    target.merge(source)
    assert target.merkle_root == root_after_first
    assert target.pinned_nodes.count("abc") == 1


def test_to_json_roundtrip():
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_node(uuid="abc", name="X", summary="Y", labels=["Entity"])
    m.update_summary("Hello")

    data = m.to_dict()
    json_str = json.dumps(data)
    loaded = KEngramManifest.from_dict(json.loads(json_str))

    assert loaded.id == m.id
    assert loaded.name == m.name
    assert loaded.pinned_nodes == m.pinned_nodes
    assert loaded.merkle_root == m.merkle_root
    assert loaded.summary == m.summary


def test_batch_mode_defers_merkle():
    """In batch mode, pin_node and pin_edge do not recompute merkle until end_batch."""
    m = KEngramManifest.create(name="Batch", kengram_type="session", group_id="g")
    empty_root = m.merkle_root

    m.begin_batch()
    m.pin_node(uuid="n1", name="A", summary="a", labels=["Entity"])
    # During batch, merkle root should NOT have changed
    assert m.merkle_root == empty_root

    m.pin_node(uuid="n2", name="B", summary="b", labels=["Entity"])
    assert m.merkle_root == empty_root

    m.pin_edge(source_uuid="n1", target_uuid="n2", name="USES", fact="fact")
    assert m.merkle_root == empty_root

    m.end_batch()
    # After end_batch, merkle root should be recomputed
    assert m.merkle_root != empty_root
    assert len(m.pinned_nodes) == 2
    assert len(m.pinned_edges) == 1


def test_batch_mode_equals_sequential():
    """Batch mode produces the same merkle root as sequential operations."""
    # Sequential
    seq = KEngramManifest.create(name="Seq", kengram_type="session", group_id="g")
    seq.pin_node(uuid="n1", name="A", summary="a", labels=["Entity"])
    seq.pin_node(uuid="n2", name="B", summary="b", labels=["Entity"])
    seq.pin_edge(source_uuid="n1", target_uuid="n2", name="USES", fact="fact")

    # Batch
    batch = KEngramManifest.create(name="Batch", kengram_type="session", group_id="g")
    batch.begin_batch()
    batch.pin_node(uuid="n1", name="A", summary="a", labels=["Entity"])
    batch.pin_node(uuid="n2", name="B", summary="b", labels=["Entity"])
    batch.pin_edge(source_uuid="n1", target_uuid="n2", name="USES", fact="fact")
    batch.end_batch()

    assert batch.merkle_root == seq.merkle_root


def test_batch_mode_flag_not_serialized():
    """_batch_mode should not appear in serialized output."""
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    d = m.to_dict()
    assert "_batch_mode" not in d
    assert "batch_mode" not in d
