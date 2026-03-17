"""kEngram manifest — the source of truth for a knowledge subgraph.

A manifest tracks pinned KG entity UUIDs, edge composite keys,
episode UUIDs, and a merkle root for provenance verification.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bonfires.kengram.hashing import hash_edge, hash_node, merkle_root


class KEngramManifest:
    """In-memory representation of a kEngram manifest."""

    def __init__(
        self,
        id: str,
        name: str,
        kengram_type: str,
        group_id: str,
        summary: str,
        pinned_nodes: list[str],
        pinned_edges: list[str],
        episodes: list[str],
        node_hashes: dict[str, str],
        node_meta: dict[str, dict[str, Any]] | None,
        edge_hashes: dict[str, str],
        merkle_root_value: str,
        parent_topic: str | None,
        created_at: str,
        updated_at: str,
    ):
        self.id = id
        self.name = name
        self.kengram_type = kengram_type
        self.group_id = group_id
        self.summary = summary
        self.pinned_nodes = pinned_nodes
        self.pinned_edges = pinned_edges
        self.episodes = episodes
        self._node_hashes = node_hashes
        self._node_meta: dict[str, dict[str, Any]] = node_meta or {}
        self._edge_hashes = edge_hashes
        self.merkle_root = merkle_root_value
        self.parent_topic = parent_topic
        self.created_at = created_at
        self.updated_at = updated_at
        self._batch_mode: bool = False

    @classmethod
    def create(
        cls,
        name: str,
        kengram_type: str,
        group_id: str,
        parent_topic: str | None = None,
    ) -> KEngramManifest:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if kengram_type == "topic":
            ke_id = f"ke-topic-{slug}"
        else:
            ke_id = f"ke-{date_str}-{slug}"

        empty_root = merkle_root([])

        return cls(
            id=ke_id,
            name=name,
            kengram_type=kengram_type,
            group_id=group_id,
            summary="",
            pinned_nodes=[],
            pinned_edges=[],
            episodes=[],
            node_hashes={},
            node_meta=None,
            edge_hashes={},
            merkle_root_value=empty_root,
            parent_topic=parent_topic,
            created_at=now,
            updated_at=now,
        )

    def begin_batch(self) -> None:
        """Suppress merkle recomputation until :meth:`end_batch` is called."""
        self._batch_mode = True

    def end_batch(self) -> None:
        """End batch mode and trigger a single merkle recompute."""
        self._batch_mode = False
        self._recompute_merkle()

    def _recompute_merkle(self) -> None:
        if self._batch_mode:
            return
        all_hashes = list(self._node_hashes.values()) + list(self._edge_hashes.values())
        self.merkle_root = merkle_root(all_hashes)
        self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def pin_node(self, uuid: str, name: str, summary: str, labels: list[str]) -> None:
        if uuid in self.pinned_nodes:
            return
        self.pinned_nodes.append(uuid)
        self._node_hashes[uuid] = hash_node(uuid, name, summary, labels)
        self._node_meta[uuid] = {"name": name, "summary": summary, "labels": labels}
        self._recompute_merkle()

    def unpin_node(self, uuid: str) -> None:
        if uuid not in self.pinned_nodes:
            return
        self.pinned_nodes.remove(uuid)
        self._node_hashes.pop(uuid, None)
        self._node_meta.pop(uuid, None)
        self._recompute_merkle()

    def pin_edge(self, source_uuid: str, target_uuid: str, name: str, fact: str) -> None:
        key = f"{source_uuid}:{target_uuid}:{name}"
        if key in self.pinned_edges:
            return
        self.pinned_edges.append(key)
        self._edge_hashes[key] = hash_edge(source_uuid, target_uuid, name, fact)
        self._recompute_merkle()

    def unpin_edge(self, key: str) -> None:
        if key not in self.pinned_edges:
            return
        self.pinned_edges.remove(key)
        self._edge_hashes.pop(key, None)
        self._recompute_merkle()

    def add_episode(self, episode_uuid: str) -> None:
        if episode_uuid not in self.episodes:
            self.episodes.append(episode_uuid)

    def update_summary(self, text: str) -> None:
        self.summary = text
        self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def merge(self, source: KEngramManifest) -> None:
        for uuid in source.pinned_nodes:
            if uuid not in self.pinned_nodes:
                self.pinned_nodes.append(uuid)
                if uuid in source._node_hashes:
                    self._node_hashes[uuid] = source._node_hashes[uuid]
                if uuid in source._node_meta:
                    self._node_meta[uuid] = source._node_meta[uuid]

        for key in source.pinned_edges:
            if key not in self.pinned_edges:
                self.pinned_edges.append(key)
                if key in source._edge_hashes:
                    self._edge_hashes[key] = source._edge_hashes[key]

        for ep in source.episodes:
            if ep not in self.episodes:
                self.episodes.append(ep)

        self._recompute_merkle()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.kengram_type,
            "name": self.name,
            "group_id": self.group_id,
            "summary": self.summary,
            "pinned_nodes": self.pinned_nodes,
            "pinned_edges": self.pinned_edges,
            "episodes": self.episodes,
            "node_hashes": self._node_hashes,
            "node_meta": self._node_meta,
            "edge_hashes": self._edge_hashes,
            "merkle_root": self.merkle_root,
            "parent_topic": self.parent_topic,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KEngramManifest:
        return cls(
            id=data["id"],
            name=data["name"],
            kengram_type=data["type"],
            group_id=data["group_id"],
            summary=data.get("summary", ""),
            pinned_nodes=data.get("pinned_nodes", []),
            pinned_edges=data.get("pinned_edges", []),
            episodes=data.get("episodes", []),
            node_hashes=data.get("node_hashes", {}),
            node_meta=data.get("node_meta"),
            edge_hashes=data.get("edge_hashes", {}),
            merkle_root_value=data.get("merkle_root", ""),
            parent_topic=data.get("parent_topic"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
