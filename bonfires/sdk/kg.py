"""Knowledge Graph service for the Bonfires SDK."""

from __future__ import annotations

from typing import Any

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import APIError, NotFoundError
from bonfires.sdk.http import _get, _post


class KGService:
    """Operations on the Bonfires knowledge graph."""

    def __init__(self, config: BonfiresConfig) -> None:
        self._config = config

    def search(self, query: str, num_results: int = 10) -> dict[str, Any]:
        """Search the KG via /delve. Returns the full response dict."""
        return _post(
            self._config,
            "/delve",
            body={
                "query": query,
                "bonfire_id": self._config.bonfire_id,
                "num_results": num_results,
                "agent_id": self._config.agent_id,
            },
        )

    def get_entity(self, uuid: str) -> dict[str, Any]:
        """Fetch a single entity by UUID. Raises NotFoundError if missing."""
        result = _get(
            self._config,
            f"/knowledge_graph/entity/{uuid}",
            params={"bonfire_id": self._config.bonfire_id},
        )
        if isinstance(result, dict) and "entity" in result:
            return result["entity"]
        return result

    def get_entities_batch(self, uuids: list[str]) -> list[dict[str, Any]]:
        """Fetch multiple entities by UUID. Raises APIError on failure."""
        result = _post(
            self._config,
            f"/knowledge_graph/entities/batch?bonfire_id={self._config.bonfire_id}",
            body={"entity_uuids": uuids},
        )
        if isinstance(result, dict) and "entities" in result:
            entities = result["entities"]
            if isinstance(entities, list):
                return entities
        raise APIError(
            "Unexpected response from entities/batch",
            status_code=0,
            response_text=str(result)[:500],
        )

    def get_entity_or_none(self, uuid: str) -> dict[str, Any] | None:
        """Fetch entity, returning None instead of raising on not-found/error."""
        try:
            return self.get_entity(uuid)
        except (NotFoundError, APIError):
            return None

    def get_entities_batch_or_none(
        self, uuids: list[str]
    ) -> list[dict[str, Any]] | None:
        """Fetch batch, returning None instead of raising on error."""
        try:
            return self.get_entities_batch(uuids)
        except APIError:
            return None

    def create_entity(
        self,
        name: str,
        labels: list[str],
        attributes: dict[str, Any],
    ) -> str:
        """Create a new entity. Returns the UUID."""
        result = _post(
            self._config,
            "/knowledge_graph/entity",
            body={
                "name": name,
                "labels": labels,
                "attributes": attributes,
                "bonfire_id": self._config.bonfire_id,
            },
        )
        uuid = result.get("uuid") if isinstance(result, dict) else None
        if not uuid:
            raise APIError(
                "No UUID in create_entity response",
                status_code=0,
                response_text=str(result)[:500],
            )
        return uuid

    def update_entity(
        self,
        uuid: str,
        name: str,
        labels: list[str],
        summary: str,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing entity's name, summary, labels, and optionally attributes."""
        body: dict[str, Any] = {
            "bonfire_id": self._config.bonfire_id,
            "name": name,
            "labels": labels,
            "summary": summary,
        }
        if attributes is not None:
            body["attributes"] = attributes
        return _post(
            self._config,
            f"/knowledge_graph/entity/{uuid}/update",
            body=body,
        )

    def create_edge(
        self,
        source_uuid: str,
        target_uuid: str,
        name: str,
        fact: str = "",
    ) -> dict[str, Any]:
        """Create an edge between two existing entities."""
        return _post(
            self._config,
            "/knowledge_graph/edge",
            body={
                "bonfire_id": self._config.bonfire_id,
                "source_uuid": source_uuid,
                "target_uuid": target_uuid,
                "edge_name": name,
                "fact": fact,
            },
        )

    def get_latest_episodes(
        self,
        agent_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch the most recent episodes for the agent.

        Returns a list of episode dicts with uuid, name, content, valid_at, etc.
        """
        aid = agent_id or self._config.agent_id
        result = _get(
            self._config,
            f"/knowledge_graph/agents/{aid}/episodes/latest",
            params={
                "bonfire_id": self._config.bonfire_id,
                "limit": limit,
            },
        )
        if isinstance(result, dict):
            return result.get("episodes", [])
        return []

    def get_latest_episode(
        self,
        agent_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch the single most recent episode. Returns None if no episodes."""
        episodes = self.get_latest_episodes(agent_id=agent_id, limit=1)
        return episodes[0] if episodes else None

    def get_node_episodes(
        self,
        node_uuid: str,
    ) -> list[dict[str, Any]]:
        """Fetch episodes that mention a specific entity node."""
        result = _get(
            self._config,
            f"/knowledge_graph/node/{node_uuid}/episodes",
            params={"bonfire_id": self._config.bonfire_id},
        )
        if isinstance(result, dict):
            return result.get("episodes", [])
        return []

    def ingest_ontology(
        self,
        ontology_path: str,
        ontology_id: str,
    ) -> dict[str, Any]:
        """Ingest an OWL/RDF ontology into the Owl_classes Weaviate collection."""
        return _post(
            self._config,
            "/knowledge_graph/ontology/ingest",
            body={
                "ontology_path": ontology_path,
                "ontology_id": ontology_id,
                "bonfire_id": self._config.bonfire_id,
            },
        )

    def match_labels(
        self,
        ontology_id: str,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Match Bonfire taxonomy labels against an ingested OWL ontology."""
        result = _post(
            self._config,
            "/knowledge_graph/ontology/match",
            body={
                "bonfire_id": self._config.bonfire_id,
                "ontology_id": ontology_id,
                "threshold": threshold,
            },
        )
        if isinstance(result, dict):
            return result.get("matches", [])
        return []

    def generate_profile(
        self,
        ontology_id: str,
        threshold: float = 0.7,
    ) -> dict[str, Any]:
        """Generate an OntologyProfile from vector-matched taxonomy labels."""
        return _post(
            self._config,
            "/knowledge_graph/ontology/generate-profile",
            body={
                "bonfire_id": self._config.bonfire_id,
                "ontology_id": ontology_id,
                "threshold": threshold,
            },
        )

    def get_edges(
        self,
        entity_uuid: str,
        direction: str = "both",
        edge_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get edges for an entity via expand endpoint. Filters by direction and type."""
        result = _post(
            self._config,
            "/knowledge_graph/expand/entity",
            body={
                "entity_uuid": entity_uuid,
                "bonfire_id": self._config.bonfire_id,
                "limit": limit,
            },
        )
        edges = result.get("edges", [])
        nodes = {n.get("uuid", ""): n for n in result.get("nodes", [])}

        filtered = []
        for edge in edges:
            src = edge.get("source_node_uuid", "")
            tgt = edge.get("target_node_uuid", "")

            if direction == "outgoing" and src != entity_uuid:
                continue
            if direction == "incoming" and tgt != entity_uuid:
                continue

            edge_name = edge.get("name", "")
            if edge_type and edge_name.upper() != edge_type.upper():
                continue

            # Enrich with node names from expand response
            other_uuid = tgt if src == entity_uuid else src
            other_node = nodes.get(other_uuid, {})

            filtered.append(
                {
                    "uuid": edge.get("uuid", ""),
                    "name": edge_name,
                    "fact": edge.get("fact", ""),
                    "source": {
                        "uuid": src,
                        "name": other_node.get("name", "")
                        if src != entity_uuid
                        else "",
                    },
                    "target": {
                        "uuid": tgt,
                        "name": other_node.get("name", "")
                        if tgt != entity_uuid
                        else "",
                    },
                    "valid_at": edge.get("valid_at"),
                    "expired_at": edge.get("expired_at"),
                    "invalid_at": edge.get("invalid_at"),
                }
            )
        return filtered

    def update_edge(
        self,
        edge_uuid: str,
        expired_at: str | None = None,
        name: str | None = None,
        fact: str | None = None,
    ) -> dict[str, Any]:
        """Update edge fields (expired_at for invalidation, name, fact)."""
        body: dict[str, Any] = {"bonfire_id": self._config.bonfire_id}
        if expired_at is not None:
            body["expired_at"] = expired_at
        if name is not None:
            body["name"] = name
        if fact is not None:
            body["fact"] = fact
        return _post(
            self._config,
            f"/knowledge_graph/edge/{edge_uuid}/update",
            body=body,
        )

    def add_triplet(
        self,
        source_uuid: str,
        source_name: str,
        target_uuid: str,
        target_name: str,
        edge_name: str,
        fact: str = "",
    ) -> dict[str, Any]:
        """Create an edge between two entities by UUID + name (triplet pattern)."""
        return _post(
            self._config,
            "/knowledge_graph/edge",
            body={
                "bonfire_id": self._config.bonfire_id,
                "source_uuid": source_uuid,
                "target_uuid": target_uuid,
                "edge_name": edge_name,
                "fact": fact or f"{source_name} {edge_name} {target_name}",
            },
        )
