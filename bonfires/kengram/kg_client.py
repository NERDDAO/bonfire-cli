"""Thin KG API client for kEngram operations.

Wraps api_get/api_post and catches SystemExit (raised on HTTP errors)
so callers receive None instead of a hard process exit.
"""

from __future__ import annotations

from typing import Any

from bonfires.api import api_get, api_post


def fetch_entity(cfg: dict[str, Any], uuid: str) -> dict[str, Any] | None:
    """Fetch a single entity by UUID from the knowledge graph."""
    try:
        return api_get(
            cfg,
            f"/knowledge_graph/entity/{uuid}",
            params={"bonfire_id": cfg["bonfire_id"]},
        )
    except SystemExit:
        return None


def fetch_entities_batch(
    cfg: dict[str, Any], uuids: list[str]
) -> list[dict[str, Any]] | None:
    """Fetch multiple entities by UUID in a single request."""
    try:
        return api_post(
            cfg,
            f"/knowledge_graph/entities/batch?bonfire_id={cfg['bonfire_id']}",
            body={"entity_uuids": uuids},
        )
    except SystemExit:
        return None


def search_entities(
    cfg: dict[str, Any], query: str, num_results: int = 10
) -> list[dict[str, Any]] | None:
    """Search the knowledge graph via the /delve endpoint."""
    try:
        return api_post(
            cfg,
            "/delve",
            body={
                "query": query,
                "bonfire_id": cfg["bonfire_id"],
                "num_results": num_results,
                "agent_id": cfg["agent_id"],
            },
        )
    except SystemExit:
        return None


def create_entity(
    cfg: dict[str, Any],
    name: str,
    labels: list[str],
    attributes: dict[str, Any],
) -> str | None:
    """Create a new entity in the knowledge graph. Returns the UUID or None."""
    try:
        result = api_post(
            cfg,
            "/knowledge_graph/entity",
            body={
                "name": name,
                "labels": labels,
                "attributes": attributes,
                "bonfire_id": cfg["bonfire_id"],
            },
        )
        return result.get("uuid") if isinstance(result, dict) else None
    except SystemExit:
        return None
