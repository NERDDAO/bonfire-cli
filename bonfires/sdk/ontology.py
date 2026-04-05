"""Ontology service for the Bonfires SDK.

Mixes API calls (ingest, match, generate) with local operations
(profile CRUD, attach/detach). Both operate on the ontology domain.
"""

from __future__ import annotations

from typing import Any

from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage
from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import NotFoundError


class OntologyService:
    """Operations on OWL ontology profiles and ontology API endpoints."""

    def __init__(self, config: BonfiresConfig, kg: Any) -> None:
        """Initialize with config and KGService (for API calls)."""
        self._config = config
        self._kg = kg
        self._storage = KEngramStorage(config.vault_dir)

    # ------------------------------------------------------------------
    # Extraction type ontology (Delve CRUD)
    # ------------------------------------------------------------------

    def get_extraction_types(self) -> dict[str, Any]:
        """Get the extraction type ontology for this bonfire."""
        from bonfires.sdk.http import _get
        return _get(
            self._config,
            f"/ontology/{self._config.bonfire_id}",
        )

    def set_extraction_types(
        self,
        entity_labels: list[dict[str, Any]],
        edge_labels: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Set the extraction type ontology for this bonfire.

        Each label is a dict with:
            name: str — type name (e.g. "NewEntitySeed")
            description: str — extraction guidance for Graphiti
            labels: list[str] — Graphiti labels (defaults to [name])
            fields: dict[str, {type, description, required}] — field definitions

        Allowed field types: str, int, float, bool, list[str]

        Example::

            client.ontology.set_extraction_types([
                {
                    "name": "QuestSeed",
                    "description": "Extracted when interaction suggests a quest",
                    "fields": {
                        "quest_name": {"type": "str", "required": True},
                        "giver_name": {"type": "str"},
                        "objective_hint": {"type": "str"},
                    }
                }
            ])
        """
        from bonfires.sdk.http import _put
        return _put(
            self._config,
            f"/ontology/{self._config.bonfire_id}",
            body={
                "entity_labels": entity_labels,
                "edge_labels": edge_labels or [],
            },
        )

    # ------------------------------------------------------------------
    # API operations (require network)
    # ------------------------------------------------------------------

    def ingest(self, ontology_path: str, ontology_id: str) -> dict[str, Any]:
        """Ingest an OWL/RDF ontology into Weaviate."""
        return self._kg.ingest_ontology(ontology_path, ontology_id)

    def match_labels(
        self, ontology_id: str, threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """Match bonfire taxonomy labels against an ingested ontology."""
        return self._kg.match_labels(ontology_id, threshold)

    def generate_profile(
        self, ontology_id: str, threshold: float = 0.7
    ) -> dict[str, Any]:
        """Generate an OntologyProfile from vector-matched taxonomy labels."""
        return self._kg.generate_profile(ontology_id, threshold)

    # ------------------------------------------------------------------
    # Local profile CRUD (no network)
    # ------------------------------------------------------------------

    def create_profile(
        self,
        name: str,
        *,
        namespaces: dict[str, str] | None = None,
        class_map: dict[str, Any] | None = None,
        object_property_map: dict[str, Any] | None = None,
        datatype_property_map: dict[str, Any] | None = None,
    ) -> Any:
        """Create a new ontology profile and save it."""
        from bonfires.kengram.ontology_profile import OntologyProfile

        prof = OntologyProfile.create(
            name=name,
            namespaces=namespaces,
            class_map=class_map,
            object_property_map=object_property_map,
            datatype_property_map=datatype_property_map,
        )
        self._storage.save_profile(prof)
        return prof

    def get_profile(self, profile_id: str) -> Any:
        """Load a profile by ID. Raises NotFoundError if missing."""
        prof = self._storage.load_profile(profile_id)
        if not prof:
            raise NotFoundError(f"Profile '{profile_id}' not found.")
        return prof

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all stored ontology profiles."""
        return self._storage.list_profiles()

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile. Returns True if it existed."""
        path = self._storage.profiles_dir / f"{profile_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def attach_profile(self, kengram_id: str, profile_id: str) -> KEngramManifest:
        """Attach a profile to a kEngram."""
        from bonfires.kengram.ontology_profile import compute_profile_hash

        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")

        prof = self._storage.load_profile(profile_id)
        if not prof:
            raise NotFoundError(f"Profile '{profile_id}' not found.")

        if profile_id in manifest.ontology_profiles:
            return manifest  # already attached

        manifest.ontology_profiles.append(profile_id)
        manifest.profile_hash = compute_profile_hash(
            manifest.ontology_profiles, self._storage.profiles_dir
        )
        self._storage.save(manifest)
        return manifest

    def detach_profile(self, kengram_id: str, profile_id: str) -> KEngramManifest:
        """Detach a profile from a kEngram."""
        from bonfires.kengram.ontology_profile import compute_profile_hash

        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")

        if profile_id not in manifest.ontology_profiles:
            return manifest  # not attached

        manifest.ontology_profiles.remove(profile_id)
        manifest.profile_hash = compute_profile_hash(
            manifest.ontology_profiles, self._storage.profiles_dir
        )
        self._storage.save(manifest)
        return manifest

    def match_and_generate(
        self,
        kengram_id: str,
        ontology_id: str,
        threshold: float = 0.7,
    ) -> Any:
        """Vector-match labels and generate a profile. Convenience method."""
        from bonfires.kengram.ontology_profile import OntologyProfile

        self._kg.match_labels(ontology_id, threshold)
        result = self._kg.generate_profile(ontology_id, threshold)

        if "id" in result:
            prof = OntologyProfile.from_dict(result)
        else:
            prof = OntologyProfile.create(
                name=f"matched-{ontology_id}",
                namespaces=result.get("namespaces"),
                class_map=result.get("class_map"),
                object_property_map=result.get("object_property_map"),
                datatype_property_map=result.get("datatype_property_map"),
            )
        self._storage.save_profile(prof)
        return prof

    def validate(self, kengram_id: str) -> dict[str, Any]:
        """Validate a kEngram against its attached ontology profiles."""
        from bonfires.kengram.ontology_pipeline import annotate_manifest, validate_graph
        from bonfires.kengram.ontology_profile import compose_profiles

        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")

        if not manifest.ontology_profiles:
            raise NotFoundError(
                "No ontology profiles attached. Attach a profile first."
            )

        profiles = self._storage.load_profiles_for_manifest(manifest)
        if not profiles:
            raise NotFoundError("Could not load any attached profiles.")

        composed = compose_profiles(profiles)
        violations = validate_graph(manifest, composed)
        annotate_manifest(manifest, composed, violations)
        self._storage.save(manifest)

        return {
            "kengram_id": manifest.id,
            "violation_count": len(violations),
            "violations": violations,
        }

    def suggest_profiles(self, kengram_id: str) -> list[dict[str, Any]]:
        """Score available profiles against a kEngram's vocabulary."""
        from bonfires.kengram.ontology_pipeline import (
            extract_vocabulary,
            identify_profiles,
        )

        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")

        vocabulary = extract_vocabulary(manifest)
        all_profiles_data = self._storage.list_profiles()
        if not all_profiles_data:
            return []

        all_profiles = [
            p
            for pid in [d["id"] for d in all_profiles_data]
            if (p := self._storage.load_profile(pid)) is not None
        ]

        scored = identify_profiles(vocabulary, all_profiles)
        return [
            {"profile_id": p.id, "name": p.name, "score": round(s, 4)}
            for p, s in scored
        ]

    def extract_gaps(self, kengram_id: str) -> list[dict[str, Any]]:
        """Extract structured gaps from ontology validation."""
        from bonfires.kengram.ontology_pipeline import (
            annotate_manifest,
            extract_gaps,
            validate_graph,
        )
        from bonfires.kengram.ontology_profile import compose_profiles

        manifest = self._storage.load(kengram_id)
        if not manifest:
            raise NotFoundError(f"kEngram '{kengram_id}' not found.")

        if not manifest.ontology_profiles:
            raise NotFoundError("No ontology profiles attached.")

        profiles = self._storage.load_profiles_for_manifest(manifest)
        if not profiles:
            raise NotFoundError("Could not load any attached profiles.")

        composed = compose_profiles(profiles)
        violations = validate_graph(manifest, composed)
        annotate_manifest(manifest, composed, violations)
        self._storage.save(manifest)
        return extract_gaps(manifest)
