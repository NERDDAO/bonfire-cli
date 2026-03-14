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


def test_export_empty_manifest():
    m = KEngramManifest.create(name="Empty", kengram_type="session", group_id="g")
    canvas = export_canvas(m, entities=[], edges=[])
    assert "nodes" in canvas
    summary_nodes = [n for n in canvas["nodes"] if n["id"] == "summary"]
    assert len(summary_nodes) == 1
