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
        rule: str | None = None,
        top_k: int = 3,
        expand: bool = True,
        num_results: int = 10,
        temperature: float = 0.3,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Semantic grammar search — cascaded (default) or scoped.

        Two modes, discriminated by the ``rule`` argument:

        - **Cascaded** (``rule=None``, default): walks the whole grammar
          tree from the origin rule, picking the contextually best
          expansion at each ``#ref#``. Returns
          ``{"mode": "cascaded", "grammar": ..., "text": "<generated>"}``.
          This is what most callers want — pass a context, get a full
          generated string back.

        - **Scoped** (``rule`` set): flat top-k matches within that one
          rule, plus optional KG expansion from the top match's id.
          Returns ``{"mode": "scoped", "presearch": {...},
          "kg_context": ...}``. Used for KG-entity presearch — pick an
          entity by grammar-label match, then delve from it in the KG.

        Args:
            query: Context string driving embedding-based selection.
            grammar: Grammar name within the configured bonfire.
            rule: Specific rule to scope to. Omit for cascading mode.
            top_k: Candidates per rule (both modes).
            expand: Scoped mode only — KG-expand from top match.
            num_results: Scoped mode only — KG results if expanding.
            temperature: Cascaded mode only — 0 = deterministic, 1 = random.
            seed: Cascaded mode only — reproducible walks.

        Returns:
            Dict tagged by ``mode`` — check ``response["mode"]`` before
            reading either ``response["text"]`` (cascaded) or
            ``response["presearch"]`` (scoped).
        """
        body: dict[str, Any] = {
            "query": query,
            "grammar": grammar,
            "top_k": top_k,
            "expand": expand,
            "num_results": num_results,
            "temperature": temperature,
            "seed": seed,
        }
        if rule is not None:
            body["rule"] = rule
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/search",
            body=body,
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

    def build(
        self,
        taxonomy_label_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the grammar builder LangGraph workflow for this bonfire.

        Builds or refreshes TrimTab grammars from KG state. Uses ontology
        types as grammars, taxonomy labels as mid-level rules, and
        LLM-clustered subclasses as leaf rules.

        Args:
            taxonomy_label_id: Optional taxonomy label ObjectId — if set,
                runs in ``single_label`` mode restricted to that label.
                Omit to run over the whole bonfire.
            dry_run: If True, compute but skip persistence.
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/build",
            body={"taxonomy_label_id": taxonomy_label_id, "dry_run": dry_run},
        )

    def update(
        self,
        grammar: str,
        id: str,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing expansion's text and/or metadata.

        Args:
            grammar: Grammar name.
            id: Expansion UUID to update.
            text: New text value, or None to leave unchanged.
            metadata: Metadata dict to merge/replace, or None to leave unchanged.

        Returns:
            Updated expansion dict with ``grammar``, ``id``, ``text``, ``metadata``.
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/update",
            body={"grammar": grammar, "id": id, "text": text, "metadata": metadata},
        )

    def remove(
        self,
        grammar: str,
        id: str,
    ) -> dict[str, Any]:
        """Remove an expansion from a grammar rule by its UUID.

        Args:
            grammar: Grammar name.
            id: Expansion UUID to remove.

        Returns:
            Dict with ``grammar``, ``id``, and ``deleted`` (bool).
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/remove",
            body={"grammar": grammar, "id": id},
        )

    def list_expansions(
        self,
        grammar: str,
        rule: str | None = None,
        filter_metadata: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_desc: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List expansions with optional metadata filtering and sorting.

        Args:
            grammar: Grammar name.
            rule: Specific rule to list. Omit to list across all rules.
            filter_metadata: Key/value pairs that expansions must match.
            sort_by: Metadata field name to sort by.
            sort_desc: Sort descending if True (default ascending).
            limit: Maximum number of expansions to return.

        Returns:
            Dict with ``grammar``, ``expansions`` (list), and ``total`` (int).
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/list",
            body={
                "grammar": grammar,
                "rule": rule,
                "filter_metadata": filter_metadata,
                "sort_by": sort_by,
                "sort_desc": sort_desc,
                "limit": limit,
            },
        )

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of all grammars for the configured bonfire.

        Returns:
            Dict with ``bonfire_id`` and ``grammars`` list.
        """
        return _get(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/summary",
        )

    def search_and_expand(
        self,
        grammar: str,
        query: str,
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Semantic search within a grammar, then KG-expand from the top match.

        Combines a scoped grammar search with a KG context expansion step,
        returning both the generated text and the raw KG contexts for the
        matched entity UUIDs.

        Args:
            grammar: Grammar name to search within.
            query: Context string driving embedding-based selection.
            top_k: Number of top candidates to retrieve before expanding.

        Returns:
            Dict with ``text``, ``center_ids`` (list of matched UUIDs), and
            ``kg_contexts`` (KG expansion results keyed by UUID).
        """
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/search-and-expand",
            body={"grammar": grammar, "query": query, "top_k": top_k},
        )

    def lens_search(
        self,
        query: str,
        grammars: list[str] | None = None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Multi-grammar lens search — runs one query across several grammars in parallel.

        Searches a set of grammars (default: quests, notes, friends, tasks)
        simultaneously and returns per-grammar result buckets. Useful for
        "what do I know about X across all my context?" queries.

        Args:
            query: Context string driving embedding-based selection.
            grammars: Grammar names to search. Defaults to the bonfire's
                standard lens set (quests, notes, friends, tasks).
            top_k: Candidates per grammar.

        Returns:
            Dict keyed by grammar name — each value is a results bucket with
            the top-k matched expansions for that grammar.
        """
        body: dict[str, Any] = {"query": query, "top_k": top_k}
        if grammars is not None:
            body["grammars"] = grammars
        return _post(
            self._config,
            f"/trimtabs/grammars/{self._config.bonfire_id}/lens-search",
            body=body,
        )
