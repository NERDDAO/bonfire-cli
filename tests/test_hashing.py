"""Tests for content-addressed hashing."""

from bonfires.kengram.hashing import hash_node, hash_edge, merkle_root


def test_hash_node_deterministic():
    h1 = hash_node(uuid="abc123", name="Rubric Pipeline", summary="Fixed", labels=["Entity"])
    h2 = hash_node(uuid="abc123", name="Rubric Pipeline", summary="Fixed", labels=["Entity"])
    assert h1 == h2
    assert len(h1) == 64

def test_hash_node_label_order_independent():
    h1 = hash_node(uuid="abc", name="X", summary="Y", labels=["Entity", "TaxonomyLabel"])
    h2 = hash_node(uuid="abc", name="X", summary="Y", labels=["TaxonomyLabel", "Entity"])
    assert h1 == h2

def test_hash_node_different_content():
    h1 = hash_node(uuid="abc", name="X", summary="Y", labels=[])
    h2 = hash_node(uuid="abc", name="X", summary="Z", labels=[])
    assert h1 != h2

def test_hash_edge_no_edge_uuid():
    h1 = hash_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed the bug")
    h2 = hash_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed the bug")
    assert h1 == h2
    assert len(h1) == 64

def test_hash_edge_different_fact():
    h1 = hash_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Fixed")
    h2 = hash_edge(source_uuid="a", target_uuid="b", name="REPAIRS", fact="Broke")
    assert h1 != h2

def test_merkle_root_empty():
    root = merkle_root([])
    assert root is not None
    assert len(root) == 64

def test_merkle_root_single():
    root = merkle_root(["abcdef1234567890" * 4])
    assert root == "abcdef1234567890" * 4

def test_merkle_root_order_independent():
    r1 = merkle_root(["aaa", "bbb", "ccc"])
    r2 = merkle_root(["ccc", "aaa", "bbb"])
    assert r1 == r2

def test_merkle_root_changes_with_content():
    r1 = merkle_root(["aaa", "bbb"])
    r2 = merkle_root(["aaa", "bbb", "ccc"])
    assert r1 != r2
