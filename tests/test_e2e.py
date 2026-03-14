"""End-to-end test: create → pin → merge → export → verify."""

from bonfires.kengram.canvas import export_canvas
from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage


def test_full_lifecycle(tmp_path):
    store = KEngramStorage(tmp_path)

    # Create topic
    topic = KEngramManifest.create(name="Rubric Pipeline", kengram_type="topic", group_id="bf:agent")
    topic.update_summary("Tracking all rubric pipeline work")
    store.save(topic)
    store.set_active(topic.id)

    # Create session
    session = KEngramManifest.create(
        name="March 13 Fixes",
        kengram_type="session",
        group_id="bf:agent",
        parent_topic=topic.id,
    )

    # Pin nodes
    session.pin_node(uuid="n1", name="Fuzzy Weight Lookup", summary="Fixed for custom rubrics", labels=["Entity"])
    session.pin_node(uuid="n2", name="Review Ref Guard", summary="Cross-contamination fix", labels=["Entity"])
    session.pin_edge(source_uuid="n1", target_uuid="n2", name="RELATES_TO", fact="Both part of rubric fixes")
    session.add_episode("ep1")
    session.update_summary("Fixed fuzzy weights and review ref guard")
    store.save(session)

    assert len(session.pinned_nodes) == 2
    assert len(session.pinned_edges) == 1
    assert session.merkle_root != topic.merkle_root

    # Merge into topic
    topic.merge(session)
    store.save(topic)

    assert len(topic.pinned_nodes) == 2
    assert "ep1" in topic.episodes

    # Merge again (idempotent)
    old_root = topic.merkle_root
    topic.merge(session)
    assert topic.merkle_root == old_root

    # Export
    entities = [
        {"uuid": "n1", "name": "Fuzzy Weight Lookup", "summary": "Fixed", "labels": ["Entity"]},
        {"uuid": "n2", "name": "Review Ref Guard", "summary": "Fixed", "labels": ["Entity"]},
    ]
    edges = [{"source_node_uuid": "n1", "target_node_uuid": "n2", "name": "RELATES_TO", "fact": "Related"}]
    canvas = export_canvas(topic, entities=entities, edges=edges)

    assert len(canvas["nodes"]) >= 3
    assert any(e.get("label") == "RELATES_TO" for e in canvas["edges"])

    path = store.save_canvas(topic.id, canvas)
    assert path.exists()

    # Verify
    from bonfires.kengram.hashing import merkle_root
    all_hashes = list(topic._node_hashes.values()) + list(topic._edge_hashes.values())
    assert merkle_root(all_hashes) == topic.merkle_root
