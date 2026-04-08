"""TrimTab service for the Bonfires SDK — calls Delve REST endpoints."""

from __future__ import annotations

from typing import Any

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.http import _delete, _get, _post


class TrimtabService:
    """Operations on TrimTab grammars stored on Delve.

    Wraps the /trimtabs/grammars/* REST endpoints. All operations are scoped
    by the configured bonfire_id.
    """

    def __init__(self, config: BonfiresConfig) -> None:
        self._config = config

    def create(self, grammar: str, rules: dict[str, list[Any]]) -> dict[str, Any]:
        """Create or replace a grammar with initial rules.

        Args:
            grammar: Grammar name.
            rules: Rules dict — values can be plain strings or
                {"text": "...", "id": "..."} objects (id is optional, used
                to associate expansions with KG entity UUIDs).
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}",
            body={"grammar": grammar, "rules": rules},
        )

    def list(self) -> dict[str, Any]:
        """List all grammars for the configured bonfire."""
        return _get(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}",
        )

    def show(self, grammar: str) -> dict[str, Any]:
        """Show full rules and expansions for a grammar."""
        return _get(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/{grammar}",
        )

    def delete(self, grammar: str) -> dict[str, Any]:
        """Delete a grammar."""
        return _delete(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/{grammar}",
        )

    def add(
        self,
        grammar: str,
        rule: str,
        text: str,
        id: str | None = None,
    ) -> dict[str, Any]:
        """Add an expansion to a grammar rule."""
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/expansions",
            body={"grammar": grammar, "rule": rule, "text": text, "id": id},
        )

    def search(
        self,
        query: str,
        grammar: str,
        rule: str = "origin",
        top_k: int = 3,
        expand: bool = True,
        num_results: int = 10,
    ) -> dict[str, Any]:
        """Semantic presearch via TrimTab grammar; optionally expand from best match in KG.

        Returns presearch matches and optionally the expanded KG context.
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/search",
            body={
                "query": query,
                "grammar": grammar,
                "rule": rule,
                "top_k": top_k,
                "expand": expand,
                "num_results": num_results,
            },
        )

    def seed(
        self,
        grammar: str,
        rule: str,
        kg_query: str,
        num_entities: int = 20,
    ) -> dict[str, Any]:
        """Seed a grammar rule with entities from the KG."""
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/seed?"
            f"grammar={grammar}&rule={rule}&kg_query={kg_query}&num_entities={num_entities}",
            body={},
        )
