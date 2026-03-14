"""Tests for kEngram vault storage."""

from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage


def test_save_and_load(tmp_path):
    store = KEngramStorage(tmp_path)
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    m.pin_node(uuid="abc", name="X", summary="Y", labels=[])
    store.save(m)
    loaded = store.load(m.id)
    assert loaded is not None
    assert loaded.id == m.id
    assert loaded.pinned_nodes == ["abc"]
    assert loaded.merkle_root == m.merkle_root


def test_load_nonexistent(tmp_path):
    store = KEngramStorage(tmp_path)
    assert store.load("ke-nonexistent") is None


def test_list_manifests(tmp_path):
    store = KEngramStorage(tmp_path)
    m1 = KEngramManifest.create(name="One", kengram_type="session", group_id="g")
    m2 = KEngramManifest.create(name="Two", kengram_type="topic", group_id="g")
    store.save(m1)
    store.save(m2)
    items = store.list_all()
    ids = [item["id"] for item in items]
    assert m1.id in ids
    assert m2.id in ids


def test_active_kengram(tmp_path):
    store = KEngramStorage(tmp_path)
    assert store.get_active() is None
    store.set_active("ke-test")
    assert store.get_active() == "ke-test"
    store.set_active("ke-other")
    assert store.get_active() == "ke-other"


def test_delete(tmp_path):
    store = KEngramStorage(tmp_path)
    m = KEngramManifest.create(name="Del", kengram_type="session", group_id="g")
    store.save(m)
    assert store.load(m.id) is not None
    store.delete(m.id)
    assert store.load(m.id) is None


def test_save_creates_directories(tmp_path):
    vault = tmp_path / "deep" / "nested" / "vault"
    store = KEngramStorage(vault)
    m = KEngramManifest.create(name="Test", kengram_type="session", group_id="g")
    store.save(m)
    assert store.load(m.id) is not None
