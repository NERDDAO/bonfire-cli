"""kEngram service for the Bonfires SDK."""

from __future__ import annotations

import json
import re
import uuid as _uuid_mod
from typing import Any

from bonfires.kengram.canvas import export_canvas
from bonfires.kengram.hashing import hash_node
from bonfires.kengram.hashing import merkle_root as compute_merkle
from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage
from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import APIError, NotFoundError

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class KEngramService:
    """Operations on kEngrams — verifiable knowledge subgraphs."""

    def __init__(self, config: BonfiresConfig, kg: Any) -> None:
        """Initialize with config and a KGService instance.

        KGService is typed as Any to avoid circular imports at module level.
        """
        self._config = config
        self._kg = kg
        self._storage = KEngramStorage(config.vault_dir)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        type: str = "session",
        parent: str | None = None,
    ) -> KEngramManifest:
        """Create a new kEngram, set it as active, and return the manifest."""
        manifest = KEngramManifest.create(
            name=name,
            kengram_type=type,
            group_id=self._config.group_id,
            parent_topic=parent,
        )
        self._storage.save(manifest)
        self._storage.set_active(manifest.id)
        return manifest

    def get(self, kengram_id: str) -> KEngramManifest:
        """Load manifest by ID. Raises NotFoundError if missing."""
        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")
        return manifest

    def get_active(self) -> KEngramManifest:
        """Load the active kEngram. Raises NotFoundError if none set."""
        active_id = self._storage.get_active()
        if not active_id:
            raise NotFoundError("No active kEngram. Create one first.")
        manifest = self._storage.load(active_id)
        if not manifest:
            raise NotFoundError(f"Active kEngram '{active_id}' not found.")
        return manifest

    def list(self) -> list[dict[str, Any]]:
        """List all kEngrams as summary dicts."""
        return self._storage.list_all()

    def get_active_id(self) -> str | None:
        """Return the active kEngram ID, or None."""
        return self._storage.get_active()

    def delete(self, kengram_id: str) -> bool:
        """Delete a kEngram. Returns True if it existed."""
        return self._storage.delete(kengram_id)

    def set_active(self, kengram_id: str) -> None:
        """Set the active kEngram. Verifies it exists first."""
        if not self._storage.load(kengram_id):
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")
        self._storage.set_active(kengram_id)

    def update_summary(self, kengram_id: str, summary: str) -> KEngramManifest:
        """Update kEngram summary text."""
        manifest = self.get(kengram_id)
        manifest.update_summary(summary)
        self._storage.save(manifest)
        return manifest

    # ------------------------------------------------------------------
    # Pin operations
    # ------------------------------------------------------------------

    def pin(
        self,
        kengram_id: str,
        uuid: str,
        *,
        name: str = "",
        summary: str = "",
        labels: list[str] | None = None,
        fetch_from_kg: bool = True,
    ) -> dict[str, Any]:
        """Pin entity to kEngram.

        If name is not provided and fetch_from_kg is True, fetches metadata
        from KG. Returns {"manifest": ..., "enrichment": ...}.
        """
        manifest = self.get(kengram_id)

        pin_name = name
        pin_summary = summary
        pin_labels = labels or []

        if not pin_name and fetch_from_kg:
            entity = self._kg.get_entity_or_none(uuid)
            if entity:
                pin_name = entity.get("name", "")
                pin_summary = entity.get("summary", "")
                pin_labels = entity.get("labels", [])

        manifest.pin_node(
            uuid=uuid, name=pin_name, summary=pin_summary, labels=pin_labels
        )

        enrichment: dict[str, Any] = {}
        if manifest.ontology_profiles:
            from bonfires.kengram.ontology_enrichment import enrich_on_pin

            profiles = self._storage.load_profiles_for_manifest(manifest)
            enrichment = enrich_on_pin(manifest, uuid, profiles)

        self._storage.save(manifest)
        return {"manifest": manifest, "enrichment": enrichment}

    def unpin(self, kengram_id: str, uuid: str) -> KEngramManifest:
        """Unpin entity from kEngram."""
        manifest = self.get(kengram_id)
        manifest.unpin_node(uuid)
        self._storage.save(manifest)
        return manifest

    def add_edge(
        self,
        kengram_id: str,
        source_uuid: str,
        target_uuid: str,
        name: str,
        fact: str = "",
        *,
        sync_to_kg: bool = True,
    ) -> dict[str, Any]:
        """Add edge to kEngram. Optionally creates in KG too.

        Returns: {"manifest": ..., "kg_synced": bool, "warnings": [...]}
        """
        manifest = self.get(kengram_id)

        if source_uuid not in manifest.pinned_nodes:
            raise NotFoundError(f"Source '{source_uuid}' is not pinned.")
        if target_uuid not in manifest.pinned_nodes:
            raise NotFoundError(f"Target '{target_uuid}' is not pinned.")

        kg_synced = False
        if sync_to_kg:
            try:
                self._kg.create_edge(source_uuid, target_uuid, name, fact)
                kg_synced = True
            except APIError:
                pass

        manifest.pin_edge(
            source_uuid=source_uuid, target_uuid=target_uuid, name=name, fact=fact
        )

        warnings: list[str] = []
        if manifest.ontology_profiles:
            from bonfires.kengram.ontology_enrichment import validate_edge_pin
            from bonfires.kengram.ontology_profile import compose_profiles

            edge_profiles = self._storage.load_profiles_for_manifest(manifest)
            if edge_profiles:
                composed = compose_profiles(edge_profiles)
                warnings = validate_edge_pin(
                    manifest, source_uuid, target_uuid, name, composed
                )

        self._storage.save(manifest)
        return {"manifest": manifest, "kg_synced": kg_synced, "warnings": warnings}

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def batch(
        self,
        kengram_id: str,
        changeset: dict[str, Any],
        *,
        sync_to_kg: bool = False,
        export_canvas_flag: bool = False,
    ) -> dict[str, Any]:
        """Apply a batch changeset (nodes + edges) to kEngram.

        Returns: {"manifest": ..., "nodes_added": int, "edges_added": int,
                  "generated_uuids": {name: uuid}, "kg_push_failures": [...]}
        """
        manifest = self.get(kengram_id)

        nodes = changeset.get("nodes", [])
        edges = changeset.get("edges", [])

        manifest.begin_batch()

        name_to_uuid: dict[str, str] = {}
        generated_uuids: dict[str, str] = {}
        nodes_added = 0
        kg_push_failures: list[str] = []

        for node in nodes:
            node_uuid = node.get("uuid", "auto")
            node_name = node.get("name", "")
            node_summary = node.get("summary", "")
            node_labels = node.get("labels", [])

            if node_uuid == "auto" and sync_to_kg:
                try:
                    kg_uuid = self._kg.create_entity(
                        name=node_name,
                        labels=node_labels,
                        attributes={"summary": node_summary} if node_summary else {},
                    )
                    node_uuid = kg_uuid
                    generated_uuids[node_name] = node_uuid
                except APIError:
                    kg_push_failures.append(node_name)
                    node_uuid = str(_uuid_mod.uuid4())
                    generated_uuids[node_name] = node_uuid
            elif node_uuid == "auto":
                node_uuid = str(_uuid_mod.uuid4())
                generated_uuids[node_name] = node_uuid

            manifest.pin_node(
                uuid=node_uuid,
                name=node_name,
                summary=node_summary,
                labels=node_labels,
            )
            name_to_uuid[node_name] = node_uuid
            nodes_added += 1

        edges_added = 0
        edge_errors: list[str] = []
        for edge_item in edges:
            src = self._resolve_name(edge_item["source"], name_to_uuid, manifest)
            tgt = self._resolve_name(edge_item["target"], name_to_uuid, manifest)
            if not src or not tgt:
                err = f"Cannot resolve edge: {edge_item['source']} -> {edge_item['target']}"
                edge_errors.append(err)
                continue
            manifest.pin_edge(
                source_uuid=src,
                target_uuid=tgt,
                name=edge_item.get("name", "RELATED_TO"),
                fact=edge_item.get("fact", ""),
            )
            edges_added += 1

        manifest.end_batch()

        if edge_errors:
            # Save what we have, but report errors
            self._storage.save(manifest)
            return {
                "manifest": manifest,
                "nodes_added": nodes_added,
                "edges_added": edges_added,
                "generated_uuids": generated_uuids,
                "kg_push_failures": kg_push_failures,
                "edge_errors": edge_errors,
            }

        self._storage.save(manifest)

        # Canvas export
        if export_canvas_flag:
            self._export_canvas(manifest)

        # KG edge sync
        if sync_to_kg:
            for edge_item in edges:
                src = self._resolve_name(edge_item["source"], name_to_uuid, manifest)
                tgt = self._resolve_name(edge_item["target"], name_to_uuid, manifest)
                if src and tgt:
                    try:
                        self._kg.create_edge(
                            src,
                            tgt,
                            edge_item.get("name", "RELATED_TO"),
                            edge_item.get("fact", ""),
                        )
                    except (APIError, Exception):
                        pass

        return {
            "manifest": manifest,
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "generated_uuids": generated_uuids,
            "kg_push_failures": kg_push_failures,
            "edge_errors": [],
        }

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, target_id: str, source_id: str) -> KEngramManifest:
        """Merge source kEngram into target."""
        target = self.get(target_id)
        source = self.get(source_id)
        target.merge(source)
        self._storage.save(target)
        return target

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def verify(self, kengram_id: str, *, local_only: bool = False) -> dict[str, Any]:
        """Verify integrity — hash comparison + KG sync status.

        Returns full result dict with: status, merkle_root, recomputed_root,
        nodes, canvas_modified, profile_hash_status, plan_structure.
        """
        manifest = self.get(kengram_id)

        # Profile hash drift check
        profile_hash_status = "ok"
        if manifest.ontology_profiles:
            from bonfires.kengram.ontology_profile import compute_profile_hash

            current_hash = compute_profile_hash(
                manifest.ontology_profiles, self._storage.profiles_dir
            )
            if current_hash != manifest.profile_hash:
                profile_hash_status = "drift"

        node_results: dict[str, dict[str, str]] = {}
        canvas_modified = 0

        if not local_only and manifest.pinned_nodes:
            fetched = self._kg.get_entities_batch_or_none(manifest.pinned_nodes)
            if fetched is not None:
                entity_map: dict[str, dict[str, Any]] = {
                    str(e["uuid"]): e for e in fetched
                }
                kg_node_hashes: dict[str, str] = {}

                for node_uuid in manifest.pinned_nodes:
                    entity = entity_map.get(node_uuid)
                    if entity is None:
                        kg_node_hashes[node_uuid] = manifest._node_hashes.get(
                            node_uuid, ""
                        )
                        node_results[node_uuid] = {"status": "not_in_kg"}
                        continue
                    kg_hash = hash_node(
                        node_uuid,
                        str(entity.get("name", "")),
                        str(entity.get("summary", "")),
                        list(entity.get("labels", [])),
                    )
                    kg_node_hashes[node_uuid] = kg_hash
                    stored_hash = manifest._node_hashes.get(node_uuid, "")
                    if kg_hash == stored_hash:
                        node_results[node_uuid] = {"status": "ok"}
                    else:
                        node_results[node_uuid] = {
                            "status": "drift",
                            "stored_hash": stored_hash,
                            "kg_hash": kg_hash,
                        }

                # Canvas diff
                canvas_dirty = self._check_canvas_diff(manifest)
                for dirty_uuid, info in canvas_dirty.items():
                    node_results[dirty_uuid] = info
                canvas_modified = len(canvas_dirty)

                all_hashes = list(kg_node_hashes.values()) + list(
                    manifest._edge_hashes.values()
                )
                recomputed = compute_merkle(all_hashes)
                verified = recomputed == manifest.merkle_root

                plan_structure = self._verify_plan_structure(manifest)

                return {
                    "status": "verified"
                    if verified and canvas_modified == 0
                    else "drift",
                    "id": manifest.id,
                    "merkle_root": manifest.merkle_root,
                    "recomputed_root": recomputed,
                    "nodes": node_results,
                    "canvas_modified": canvas_modified,
                    "profile_hash_status": profile_hash_status,
                    "plan_structure": plan_structure,
                }

        # Local-only verification
        for node_uuid in manifest.pinned_nodes:
            node_results[node_uuid] = {"status": "local_only"}

        all_hashes = list(manifest._node_hashes.values()) + list(
            manifest._edge_hashes.values()
        )
        recomputed = compute_merkle(all_hashes)
        verified = recomputed == manifest.merkle_root
        plan_structure = self._verify_plan_structure(manifest)

        return {
            "status": "verified" if verified else "drift",
            "id": manifest.id,
            "merkle_root": manifest.merkle_root,
            "recomputed_root": recomputed,
            "nodes": node_results,
            "canvas_modified": 0,
            "profile_hash_status": profile_hash_status,
            "plan_structure": plan_structure,
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        kengram_id: str,
        *,
        format: str = "canvas",
        serialization: str = "turtle",
    ) -> str:
        """Export kEngram. Returns file path of exported file."""
        manifest = self.get(kengram_id)
        entities, edges = self._collect_entities_edges(manifest)

        if format == "owl":
            return self._export_owl(manifest, serialization)
        if format == "plan":
            return self._export_plan(manifest, entities, edges)
        return self._export_canvas_with_verify(manifest, entities, edges)

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def push(
        self,
        kengram_id: str,
        *,
        changes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Push local-only nodes and edges to the canonical KG.

        Handles entity creation, UUID remapping, edge migration,
        stale edge cleanup, and canvas change processing.
        """
        manifest = self.get(kengram_id)

        nodes_pushed = 0
        nodes_skipped = 0
        pushed_uuid_pairs: list[tuple[str, str]] = []

        for node_uuid in manifest.pinned_nodes:
            existing = self._kg.get_entity_or_none(node_uuid)
            if existing is not None:
                nodes_skipped += 1
                continue
            meta = manifest._node_meta.get(node_uuid, {})
            node_name = str(meta.get("name", ""))
            node_summary = str(meta.get("summary", ""))
            node_labels = list(meta.get("labels", []))
            attributes: dict[str, Any] = (
                {"summary": node_summary} if node_summary else {}
            )
            try:
                result_uuid = self._kg.create_entity(node_name, node_labels, attributes)
                nodes_pushed += 1
                pushed_uuid_pairs.append((node_uuid, result_uuid))
            except APIError:
                nodes_skipped += 1

        # Re-pin with canonical UUIDs
        for local_uuid, canonical_uuid in pushed_uuid_pairs:
            entity = self._kg.get_entity_or_none(canonical_uuid)
            if entity:
                new_name = str(entity.get("name", ""))
                new_summary = str(entity.get("summary", ""))
                new_labels = list(entity.get("labels", []))
                new_hash = hash_node(canonical_uuid, new_name, new_summary, new_labels)
                if canonical_uuid != local_uuid:
                    manifest._node_hashes.pop(local_uuid, None)
                    manifest._node_meta.pop(local_uuid, None)
                    if local_uuid in manifest.pinned_nodes:
                        manifest.pinned_nodes.remove(local_uuid)
                        manifest.pinned_nodes.append(canonical_uuid)
                manifest._node_hashes[canonical_uuid] = new_hash
                manifest._node_meta[canonical_uuid] = {
                    "name": new_name,
                    "summary": new_summary,
                    "labels": new_labels,
                }

        # Remap edge composite keys
        uuid_remap: dict[str, str] = {
            local: canonical for local, canonical in pushed_uuid_pairs
        }
        pinned_set = set(manifest.pinned_nodes)
        stale_edges_dropped: list[str] = []
        edges_remapped = 0

        for edge_key in list(manifest.pinned_edges):
            parts = edge_key.split(":", 2)
            if len(parts) != 3:
                continue
            src, tgt, ename = parts
            new_src = uuid_remap.get(src, src)
            new_tgt = uuid_remap.get(tgt, tgt)

            if new_src not in pinned_set or new_tgt not in pinned_set:
                manifest.unpin_edge(edge_key)
                stale_edges_dropped.append(ename)
                continue

            if new_src != src or new_tgt != tgt:
                manifest.unpin_edge(edge_key)
                manifest.pin_edge(
                    source_uuid=new_src, target_uuid=new_tgt, name=ename, fact=""
                )
                edges_remapped += 1

        if pushed_uuid_pairs or edges_remapped or stale_edges_dropped:
            manifest._recompute_merkle()

        # Push edges
        edges_pushed = 0
        edges_skipped = 0
        for edge_key in manifest.pinned_edges:
            parts = edge_key.split(":", 2)
            if len(parts) != 3:
                edges_skipped += 1
                continue
            source_uuid, target_uuid, edge_name = parts
            try:
                self._kg.create_edge(source_uuid, target_uuid, edge_name, "")
                edges_pushed += 1
            except APIError:
                edges_skipped += 1

        # Canvas changes processing
        nodes_updated = 0
        nodes_created = 0
        edges_created = 0

        if changes:
            result = self._process_canvas_changes(manifest, changes)
            nodes_updated = result["nodes_updated"]
            nodes_created = result["nodes_created"]
            edges_created = result["edges_created"]

        self._storage.save(manifest)

        return {
            "kengram_id": manifest.id,
            "nodes_pushed": nodes_pushed,
            "nodes_skipped": nodes_skipped,
            "edges_pushed": edges_pushed,
            "edges_skipped": edges_skipped,
            "edges_remapped": edges_remapped,
            "stale_edges_dropped": len(stale_edges_dropped),
            "nodes_updated": nodes_updated,
            "nodes_created": nodes_created,
            "edges_created": edges_created,
            "merkle_root": manifest.merkle_root,
        }

    # ------------------------------------------------------------------
    # Repin
    # ------------------------------------------------------------------

    def repin(self, kengram_id: str, uuid: str) -> dict[str, Any]:
        """Re-fetch entity from KG and update hash in kEngram."""
        manifest = self.get(kengram_id)

        if uuid not in manifest.pinned_nodes:
            raise NotFoundError(
                f"UUID '{uuid}' is not pinned in kEngram '{kengram_id}'."
            )

        entity = self._kg.get_entity_or_none(uuid)
        if not entity:
            raise NotFoundError(f"Could not fetch entity '{uuid}' from KG.")

        new_name = str(entity.get("name", ""))
        new_summary = str(entity.get("summary", ""))
        new_labels = list(entity.get("labels", []))

        old_hash = manifest._node_hashes.get(uuid, "")
        new_hash = hash_node(uuid, new_name, new_summary, new_labels)

        manifest._node_hashes[uuid] = new_hash
        manifest._node_meta[uuid] = {
            "name": new_name,
            "summary": new_summary,
            "labels": new_labels,
        }
        manifest._recompute_merkle()
        self._storage.save(manifest)

        return {
            "changed": old_hash != new_hash,
            "merkle_root": manifest.merkle_root,
        }

    # ------------------------------------------------------------------
    # Import OWL
    # ------------------------------------------------------------------

    def import_owl(
        self, kengram_id: str, file_path: str, profile_id: str
    ) -> dict[str, Any]:
        """Import entities from an OWL/RDF file using inverted profile mappings."""
        from pathlib import Path

        from rdflib import RDF, RDFS, Graph, URIRef

        from bonfires.kengram.ontology_profile import invert_profile

        manifest = self.get(kengram_id)
        prof = self._storage.load_profile(profile_id)
        if not prof:
            raise NotFoundError(f"Profile '{profile_id}' not found.")

        inverted = invert_profile(prof)
        class_to_label: dict[str, str] = inverted["class_to_label"]
        datatype_property_to_attr: dict[str, str] = inverted[
            "datatype_property_to_attr"
        ]

        graph = Graph()
        fp = Path(file_path)
        fmt: str | None = None
        suffix = fp.suffix.lower()
        if suffix in (".ttl",):
            fmt = "turtle"
        elif suffix in (".jsonld", ".json"):
            fmt = "json-ld"
        elif suffix in (".rdf", ".xml", ".owl"):
            fmt = "xml"
        graph.parse(str(fp), format=fmt)

        nodes_added = 0
        manifest.begin_batch()
        try:
            for owl_class_iri, graphiti_label in class_to_label.items():
                owl_class_ref = URIRef(owl_class_iri)
                for subject in graph.subjects(RDF.type, owl_class_ref):
                    if not isinstance(subject, URIRef):
                        continue
                    name_values = list(graph.objects(subject, RDFS.label))
                    if name_values:
                        entity_name = str(name_values[0])
                    else:
                        fragment = str(subject).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                        entity_name = fragment

                    summary_text = ""
                    for owl_prop_iri, attr_name in datatype_property_to_attr.items():
                        prop_ref = URIRef(owl_prop_iri)
                        for obj in graph.objects(subject, prop_ref):
                            val = str(obj)
                            if attr_name == "summary":
                                summary_text = val
                            break

                    entity_uuid = str(_uuid_mod.uuid4())
                    manifest.pin_node(
                        uuid=entity_uuid,
                        name=entity_name,
                        summary=summary_text,
                        labels=[graphiti_label],
                    )
                    nodes_added += 1
        finally:
            manifest.end_batch()

        self._storage.save(manifest)
        return {
            "nodes_added": nodes_added,
            "kengram_id": manifest.id,
            "merkle_root": manifest.merkle_root,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_name(
        self,
        name: str,
        name_to_uuid: dict[str, str],
        manifest: KEngramManifest,
    ) -> str | None:
        """Resolve a node name or UUID-like string to a UUID."""
        if name in name_to_uuid:
            return name_to_uuid[name]
        for node_uuid, meta in manifest._node_meta.items():
            if meta.get("name") == name:
                return node_uuid
        if _UUID_RE.match(name):
            return name
        return None

    def _collect_entities_edges(
        self, manifest: KEngramManifest
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Build entity and edge lists from manifest for export."""
        entities = []
        for node_uuid in manifest.pinned_nodes:
            meta = manifest._node_meta.get(node_uuid, {})
            entities.append(
                {
                    "uuid": node_uuid,
                    "name": meta.get("name", node_uuid[:12]),
                    "summary": meta.get("summary", ""),
                    "labels": meta.get("labels", []),
                }
            )
        edges = []
        for key in manifest.pinned_edges:
            parts = key.split(":", 2)
            if len(parts) == 3:
                edges.append(
                    {
                        "source_node_uuid": parts[0],
                        "target_node_uuid": parts[1],
                        "name": parts[2],
                        "fact": "",
                    }
                )
        return entities, edges

    def _export_canvas(self, manifest: KEngramManifest) -> str:
        """Export canvas without verify (used by batch)."""
        entities, edges = self._collect_entities_edges(manifest)
        canvas_data = export_canvas(manifest, entities=entities, edges=edges)
        path = self._storage.save_canvas(manifest.id, canvas_data)
        return str(path)

    def _export_canvas_with_verify(
        self,
        manifest: KEngramManifest,
        entities: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> str:
        """Export canvas with per-node KG sync status coloring."""
        node_status = self._verify_for_export(manifest)
        canvas_data = export_canvas(
            manifest, entities=entities, edges=edges, node_status=node_status
        )
        path = self._storage.save_canvas(manifest.id, canvas_data)
        return str(path)

    def _export_plan(
        self,
        manifest: KEngramManifest,
        entities: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> str:
        """Export as markdown plan."""
        from bonfires.kengram.plan_export import export_plan

        md = export_plan(manifest, entities, edges)
        path = self._storage.save_plan(manifest.id, manifest.name, md)
        return str(path)

    def _export_owl(self, manifest: KEngramManifest, serialization: str) -> str:
        """Export as OWL/RDF."""
        from typing import cast

        from bonfires.kengram.ontology_pipeline import (
            SerializationFormat,
            export_rdf,
            parse_to_rdf,
        )
        from bonfires.kengram.ontology_profile import compose_profiles

        if not manifest.ontology_profiles:
            raise NotFoundError(
                "No ontology profiles attached. Attach a profile first."
            )
        profiles = self._storage.load_profiles_for_manifest(manifest)
        if not profiles:
            raise NotFoundError("Could not load any attached profiles.")

        composed = compose_profiles(profiles)
        graph = parse_to_rdf(manifest, composed)
        ser_fmt = cast(SerializationFormat, serialization)
        rdf_content = export_rdf(graph, ser_fmt)
        ext_map: dict[str, str] = {
            "turtle": "ttl",
            "json-ld": "jsonld",
            "xml": "rdf",
        }
        ext = ext_map.get(serialization, "ttl")
        path = self._storage.save_export(manifest.id, rdf_content, ext)
        return str(path)

    def _check_canvas_diff(
        self, manifest: KEngramManifest
    ) -> dict[str, dict[str, Any]]:
        """Compare canvas card content against manifest node_meta."""
        import os

        canvas_path = os.path.join(
            self._config.vault_dir, "kengrams", "canvas", f"{manifest.id}.canvas"
        )
        if not os.path.isfile(canvas_path):
            return {}

        try:
            with open(canvas_path) as f:
                canvas_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

        dirty: dict[str, dict[str, Any]] = {}
        for node in canvas_data.get("nodes", []):
            if node.get("type") != "text":
                continue
            node_id = node.get("id", "")
            if node_id not in manifest._node_hashes:
                continue
            parsed = self._parse_canvas_card(node.get("text", ""))
            if parsed is None:
                continue

            meta = manifest._node_meta.get(node_id, {})
            changes: list[str] = []
            if parsed["name"] != meta.get("name", ""):
                changes.append(f"name: '{meta.get('name', '')}' -> '{parsed['name']}'")
            if parsed["summary"] != meta.get("summary", ""):
                changes.append("summary changed")
            meta_labels = sorted(meta.get("labels", []))
            canvas_labels = sorted(parsed["labels"])
            if meta_labels != canvas_labels:
                changes.append(f"labels: {meta_labels} -> {canvas_labels}")
            if changes:
                dirty[node_id] = {"status": "canvas_modified", "changes": changes}

        return dirty

    @staticmethod
    def _parse_canvas_card(text: str) -> dict[str, str | list[str]] | None:
        """Parse a canvas card's text into entity metadata."""
        lines = text.split("\n")
        if not lines or not lines[0].startswith("### "):
            return None
        name = lines[0][4:].strip()
        label_line = lines[1] if len(lines) > 1 else ""
        labels = [m.group(1) for m in re.finditer(r"\[([^\]]+)\]", label_line)]
        summary_start = 2 if labels else 1
        summary = "\n".join(lines[summary_start:]).strip()
        return {"name": name, "summary": summary, "labels": labels}

    def _verify_for_export(self, manifest: KEngramManifest) -> dict[str, str]:
        """Quick verify for canvas coloring. Returns uuid -> status."""
        if not manifest.pinned_nodes:
            return {}

        fetched = self._kg.get_entities_batch_or_none(manifest.pinned_nodes)
        if fetched is None:
            return {}

        entity_map: dict[str, dict[str, Any]] = {str(e["uuid"]): e for e in fetched}
        status: dict[str, str] = {}
        for node_uuid in manifest.pinned_nodes:
            entity = entity_map.get(node_uuid)
            if entity is None:
                status[node_uuid] = "NOT_IN_KG"
                continue
            kg_hash = hash_node(
                node_uuid,
                str(entity.get("name", "")),
                str(entity.get("summary", "")),
                list(entity.get("labels", [])),
            )
            stored_hash = manifest._node_hashes.get(node_uuid, "")
            status[node_uuid] = "OK" if kg_hash == stored_hash else "DRIFT"
        return status

    def _verify_plan_structure(self, manifest: KEngramManifest) -> dict[str, Any]:
        """Check plan-specific structure: orphan tasks and DEPENDS_ON cycles."""
        goal_nodes = [
            u
            for u in manifest.pinned_nodes
            if "Goal" in (manifest._node_meta.get(u, {}).get("labels", []))
        ]
        if not goal_nodes:
            return {}

        task_nodes = [
            u
            for u in manifest.pinned_nodes
            if "Task" in (manifest._node_meta.get(u, {}).get("labels", []))
            and "Goal" not in (manifest._node_meta.get(u, {}).get("labels", []))
        ]
        if not task_nodes:
            return {}

        decomp_targets: set[str] = set()
        for key in manifest.pinned_edges:
            parts = key.split(":", 2)
            if len(parts) == 3 and parts[2] == "DECOMPOSES_INTO":
                decomp_targets.add(parts[1])
        orphans = [u for u in task_nodes if u not in decomp_targets]

        from bonfires.kengram.plan_export import topological_sort

        depends_edges: list[dict[str, str]] = []
        for key in manifest.pinned_edges:
            parts = key.split(":", 2)
            if len(parts) == 3 and parts[2] == "DEPENDS_ON":
                depends_edges.append(
                    {
                        "source_node_uuid": parts[0],
                        "target_node_uuid": parts[1],
                        "name": "DEPENDS_ON",
                    }
                )
        sorted_uuids = topological_sort(task_nodes, depends_edges)
        cycle_members = [
            u for u in task_nodes if u not in sorted_uuids[: len(task_nodes)]
        ]

        return {
            "orphan_tasks": orphans,
            "cycle_members": cycle_members,
        }

    def _process_canvas_changes(
        self,
        manifest: KEngramManifest,
        changes: dict[str, Any],
    ) -> dict[str, int]:
        """Process canvas changes: dirty nodes, new nodes, new edges."""
        dirty = changes.get("dirty", {})
        new_nodes = changes.get("new_nodes", {})
        new_edges = changes.get("new_edges", [])

        nodes_updated = 0
        nodes_created = 0
        edges_created = 0

        # 1. Update dirty nodes
        for node_uuid, node_data in dirty.items():
            node_name = str(node_data.get("name", ""))
            node_summary = str(node_data.get("summary", ""))
            node_labels = list(node_data.get("labels", []))
            try:
                self._kg.update_entity(node_uuid, node_name, node_labels, node_summary)
                nodes_updated += 1
                # Audit edge
                try:
                    self._kg.create_edge(
                        node_uuid,
                        node_uuid,
                        "MODIFIED_VIA_KENGRAM",
                        f"Entity updated via kEngram canvas: name='{node_name}', labels={node_labels}",
                    )
                except APIError:
                    pass
                # Re-pin with canonical data
                canonical = self._kg.get_entity_or_none(node_uuid)
                if canonical:
                    canon_name = str(canonical.get("name", node_name))
                    canon_summary = str(canonical.get("summary", node_summary))
                    canon_labels = list(canonical.get("labels", node_labels))
                else:
                    canon_name, canon_summary, canon_labels = (
                        node_name,
                        node_summary,
                        node_labels,
                    )
                new_hash = hash_node(node_uuid, canon_name, canon_summary, canon_labels)
                manifest._node_hashes[node_uuid] = new_hash
                manifest._node_meta[node_uuid] = {
                    "name": canon_name,
                    "summary": canon_summary,
                    "labels": canon_labels,
                }
            except APIError:
                pass

        # 2. Create new canvas nodes
        canvas_id_to_uuid: dict[str, str] = {}
        for canvas_id, node_data in new_nodes.items():
            node_name = str(node_data.get("name", ""))
            node_summary = str(node_data.get("summary", ""))
            node_labels = list(node_data.get("labels", []))
            attributes: dict[str, Any] = (
                {"summary": node_summary} if node_summary else {}
            )
            try:
                result_uuid = self._kg.create_entity(node_name, node_labels, attributes)
                nodes_created += 1
                canvas_id_to_uuid[canvas_id] = result_uuid
                manifest.pinned_nodes.append(result_uuid)
                new_hash = hash_node(result_uuid, node_name, node_summary, node_labels)
                manifest._node_hashes[result_uuid] = new_hash
                manifest._node_meta[result_uuid] = {
                    "name": node_name,
                    "summary": node_summary,
                    "labels": node_labels,
                }
            except APIError:
                pass

        # 3. Create new canvas edges
        for edge_data in new_edges:
            from_id = str(edge_data.get("from", ""))
            to_id = str(edge_data.get("to", ""))
            edge_label = str(edge_data.get("label", ""))
            from_uuid = canvas_id_to_uuid.get(from_id, from_id)
            to_uuid = canvas_id_to_uuid.get(to_id, to_id)
            if from_uuid and to_uuid and edge_label:
                try:
                    self._kg.create_edge(from_uuid, to_uuid, edge_label, "")
                    edges_created += 1
                    edge_key = f"{from_uuid}:{to_uuid}:{edge_label}"
                    manifest.pinned_edges.append(edge_key)
                    manifest._edge_hashes[edge_key] = edge_key
                except APIError:
                    pass

        if nodes_updated or nodes_created or edges_created:
            manifest._recompute_merkle()

        return {
            "nodes_updated": nodes_updated,
            "nodes_created": nodes_created,
            "edges_created": edges_created,
        }
