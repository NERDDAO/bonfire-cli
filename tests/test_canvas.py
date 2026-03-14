"""Tests for kEngram canvas export."""

from bonfires.kengram.canvas import export_canvas
from bonfires.kengram.manifest import KEngramManifest


def _make_manifest_with_data():
    m = KEngramManifest.create(name="Test Export", kengram_type="session", group_id="g")
    m.update_summary("This is a test kEngram")
    m.pin_node(uuid="n1", name="Entity A", summary="First entity", labels=["Entity"])
    m.pin_node(uuid="n2", name="Entity B", summary="Second entity", labels=["Entity", "TaxonomyLabel"])
    m.pin_edge(source_uuid="n1", target_uuid="n2", name="RELATES_TO", fact="They are related")

    entities = [
        {"uuid": "n1", "name": "Entity A", "summary": "First entity", "labels": ["Entity"]},
        {"uuid": "n2", "name": "Entity B", "summary": "Second entity", "labels": ["Entity", "TaxonomyLabel"]},
    ]
    edges = [
        {"source_node_uuid": "n1", "target_node_uuid": "n2", "name": "RELATES_TO", "fact": "They are related"},
    ]
    return m, entities, edges


def test_export_produces_valid_canvas():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    assert "nodes" in canvas
    assert "edges" in canvas
    assert len(canvas["nodes"]) > 0


def test_export_has_summary_node():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    summary_nodes = [n for n in canvas["nodes"] if n["id"] == "summary"]
    assert len(summary_nodes) == 1
    assert "This is a test kEngram" in summary_nodes[0]["text"]


def test_export_has_entity_nodes():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    node_ids = {n["id"] for n in canvas["nodes"]}
    assert "n1" in node_ids
    assert "n2" in node_ids


def test_export_has_edges():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    assert len(canvas["edges"]) >= 1
    edge_labels = [e.get("label", "") for e in canvas["edges"]]
    assert "RELATES_TO" in edge_labels


def test_export_has_metadata_node():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    meta_nodes = [n for n in canvas["nodes"] if n["id"] == "metadata"]
    assert len(meta_nodes) == 1
    assert m.merkle_root[:16] in meta_nodes[0]["text"]


def test_export_grid_no_gaps_with_unpinned_entities():
    """When entities list has items not in pinned_set, grid indices stay contiguous."""
    m = KEngramManifest.create(name="Grid Test", kengram_type="session", group_id="g")
    m.pin_node(uuid="n1", name="Alpha", summary="First", labels=["Entity"])
    m.pin_node(uuid="n3", name="Charlie", summary="Third", labels=["Entity"])

    entities = [
        {"uuid": "n1", "name": "Alpha", "summary": "First", "labels": ["Entity"]},
        {"uuid": "n2", "name": "Bravo", "summary": "Second (not pinned)", "labels": ["Entity"]},
        {"uuid": "n3", "name": "Charlie", "summary": "Third", "labels": ["Entity"]},
    ]
    edges: list[dict[str, str]] = []
    canvas = export_canvas(m, entities=entities, edges=edges)

    entity_nodes = [n for n in canvas["nodes"] if n["id"] in ("n1", "n3")]
    assert len(entity_nodes) == 2

    # Both should be on row 0 (rendered_idx 0 and 1), no gap from skipped n2
    positions = sorted([(n["x"], n["y"]) for n in entity_nodes])
    # col 0 -> x = (0-1)*(280+40) = -320, col 1 -> x = (1-1)*(280+40) = 0
    assert positions[0] == (-320, -100)
    assert positions[1] == (0, -100)


def test_export_empty_manifest():
    m = KEngramManifest.create(name="Empty", kengram_type="session", group_id="g")
    canvas = export_canvas(m, entities=[], edges=[])
    assert "nodes" in canvas
    summary_nodes = [n for n in canvas["nodes"] if n["id"] == "summary"]
    assert len(summary_nodes) == 1
