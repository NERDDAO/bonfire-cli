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
    # Only real edges, no summary-to-node edges
    real_edges = [e for e in canvas["edges"] if not e["id"].startswith("s-")]
    assert len(real_edges) >= 1
    edge_labels = [e.get("label", "") for e in real_edges]
    assert "RELATES_TO" in edge_labels


def test_export_has_metadata_node():
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)
    meta_nodes = [n for n in canvas["nodes"] if n["id"] == "metadata"]
    assert len(meta_nodes) == 1
    assert m.merkle_root[:16] in meta_nodes[0]["text"]


def test_export_topology_layout():
    """Nodes connected by edges should be on different layers (y positions)."""
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)

    node_positions = {n["id"]: (n["x"], n["y"]) for n in canvas["nodes"]}
    # n1 -> n2 via RELATES_TO, so n1 should be layer 0, n2 layer 1
    assert "n1" in node_positions
    assert "n2" in node_positions
    assert node_positions["n1"][1] < node_positions["n2"][1], "source should be above target"


def test_export_edge_sides_vertical():
    """When source is above target, edge should go bottom->top."""
    m, entities, edges = _make_manifest_with_data()
    canvas = export_canvas(m, entities=entities, edges=edges)

    real_edges = [e for e in canvas["edges"] if e.get("label") == "RELATES_TO"]
    assert len(real_edges) == 1
    edge = real_edges[0]
    assert edge["fromSide"] == "bottom"
    assert edge["toSide"] == "top"


def test_export_no_gaps_with_unpinned_entities():
    """Unpinned entities in the entities list are excluded from layout."""
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
    # Both disconnected, same layer, side by side
    ys = {n["y"] for n in entity_nodes}
    assert len(ys) == 1, "disconnected nodes should be on the same layer"


def test_export_empty_manifest():
    m = KEngramManifest.create(name="Empty", kengram_type="session", group_id="g")
    canvas = export_canvas(m, entities=[], edges=[])
    assert "nodes" in canvas
    summary_nodes = [n for n in canvas["nodes"] if n["id"] == "summary"]
    assert len(summary_nodes) == 1


def test_export_three_layer_graph():
    """A chain A->B->C should produce 3 layers."""
    m = KEngramManifest.create(name="Chain", kengram_type="session", group_id="g")
    m.pin_node(uuid="a", name="A", summary="", labels=["Entity"])
    m.pin_node(uuid="b", name="B", summary="", labels=["Entity"])
    m.pin_node(uuid="c", name="C", summary="", labels=["Entity"])
    m.pin_edge(source_uuid="a", target_uuid="b", name="LEADS_TO", fact="")
    m.pin_edge(source_uuid="b", target_uuid="c", name="LEADS_TO", fact="")

    entities = [
        {"uuid": "a", "name": "A", "summary": "", "labels": ["Entity"]},
        {"uuid": "b", "name": "B", "summary": "", "labels": ["Entity"]},
        {"uuid": "c", "name": "C", "summary": "", "labels": ["Entity"]},
    ]
    edges = [
        {"source_node_uuid": "a", "target_node_uuid": "b", "name": "LEADS_TO"},
        {"source_node_uuid": "b", "target_node_uuid": "c", "name": "LEADS_TO"},
    ]
    canvas = export_canvas(m, entities=entities, edges=edges)

    pos = {n["id"]: n["y"] for n in canvas["nodes"] if n["id"] in ("a", "b", "c")}
    assert pos["a"] < pos["b"] < pos["c"], "chain should produce ascending y positions"
