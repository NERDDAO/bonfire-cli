"""OWL L2 ontology profiles — mapping between OWL ontologies and Graphiti KG labels.

An OntologyProfile defines how OWL classes and properties map to internal
Graphiti entity types and attributes. Profiles can be composed (left-to-right
merge) and inverted for import-time resolution.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

# Always-present kEngram base namespace.
KE_NAMESPACE_URI = "http://bonfires.ai/kengram/ns#"
KE_NAMESPACE_PREFIX = "ke"


class OntologyProfile:
    """In-memory representation of an OWL-to-Graphiti ontology profile."""

    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        namespaces: dict[str, str],
        class_map: dict[str, dict[str, Any]],
        object_property_map: dict[str, dict[str, Any]],
        datatype_property_map: dict[str, dict[str, Any]],
    ):
        self.id = id
        self.name = name
        self.version = version
        self.namespaces = namespaces
        self.class_map = class_map
        self.object_property_map = object_property_map
        self.datatype_property_map = datatype_property_map

    @classmethod
    def create(
        cls,
        name: str,
        version: str = "1.0.0",
        namespaces: dict[str, str] | None = None,
        class_map: dict[str, dict[str, Any]] | None = None,
        object_property_map: dict[str, dict[str, Any]] | None = None,
        datatype_property_map: dict[str, dict[str, Any]] | None = None,
    ) -> OntologyProfile:
        """Factory — creates a new profile with a slug-based ID."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        profile_id = f"profile-{slug}"
        merged_namespaces: dict[str, str] = {KE_NAMESPACE_PREFIX: KE_NAMESPACE_URI}
        if namespaces:
            merged_namespaces.update(namespaces)
        return cls(
            id=profile_id,
            name=name,
            version=version,
            namespaces=merged_namespaces,
            class_map=class_map or {},
            object_property_map=object_property_map or {},
            datatype_property_map=datatype_property_map or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "namespaces": self.namespaces,
            "class_map": self.class_map,
            "object_property_map": self.object_property_map,
            "datatype_property_map": self.datatype_property_map,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OntologyProfile:
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            namespaces=data.get("namespaces", {KE_NAMESPACE_PREFIX: KE_NAMESPACE_URI}),
            class_map=data.get("class_map", {}),
            object_property_map=data.get("object_property_map", {}),
            datatype_property_map=data.get("datatype_property_map", {}),
        )


def compose_profiles(profiles: list[OntologyProfile]) -> OntologyProfile:
    """Merge profiles left-to-right; later entries override earlier ones.

    - ``namespaces``: union, later wins on key collision.
    - ``class_map``, ``object_property_map``, ``datatype_property_map``: later
      entry replaces the entire per-key dict when keys collide.
    - Always injects ``ke: http://bonfires.ai/kengram/ns#`` as a baseline
      namespace regardless of source profiles.

    Returns a synthetic profile with id ``profile-composed``.
    """
    composed_namespaces: dict[str, str] = {KE_NAMESPACE_PREFIX: KE_NAMESPACE_URI}
    composed_class_map: dict[str, dict[str, Any]] = {}
    composed_object_property_map: dict[str, dict[str, Any]] = {}
    composed_datatype_property_map: dict[str, dict[str, Any]] = {}

    for profile in profiles:
        composed_namespaces.update(profile.namespaces)
        composed_class_map.update(profile.class_map)
        composed_object_property_map.update(profile.object_property_map)
        composed_datatype_property_map.update(profile.datatype_property_map)

    # Ensure ke namespace is never overwritten by a profile.
    composed_namespaces[KE_NAMESPACE_PREFIX] = KE_NAMESPACE_URI

    names = ", ".join(p.name for p in profiles) if profiles else "empty"

    return OntologyProfile(
        id="profile-composed",
        name=f"Composed({names})",
        version="0.0.0",
        namespaces=composed_namespaces,
        class_map=composed_class_map,
        object_property_map=composed_object_property_map,
        datatype_property_map=composed_datatype_property_map,
    )


def compute_profile_hash(profile_ids: list[str], profiles_dir: Path) -> str:
    """Compute a SHA-256 hash of the concatenated profile file contents.

    Files are read in the order given by ``profile_ids``. Missing files are
    silently skipped (the hash reflects what is actually on disk).
    """
    h = hashlib.sha256()
    for profile_id in profile_ids:
        path = profiles_dir / f"{profile_id}.json"
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()


def invert_profile(profile: OntologyProfile) -> dict[str, Any]:
    """Invert a profile's mappings for use during OWL import.

    Returns a dict with three sub-dicts:

    - ``class_to_label``: OWL class IRI → Graphiti entity label
    - ``object_property_to_edge``: OWL object property IRI → Graphiti edge name
    - ``datatype_property_to_attr``: OWL datatype property IRI → attribute name
    """
    class_to_label: dict[str, str] = {}
    for owl_class, mapping in profile.class_map.items():
        label = mapping.get("graphiti_label")
        if isinstance(label, str) and label:
            class_to_label[owl_class] = label

    object_property_to_edge: dict[str, str] = {}
    for owl_prop, mapping in profile.object_property_map.items():
        edge_name = mapping.get("graphiti_edge")
        if isinstance(edge_name, str) and edge_name:
            object_property_to_edge[owl_prop] = edge_name

    datatype_property_to_attr: dict[str, str] = {}
    for owl_prop, mapping in profile.datatype_property_map.items():
        attr_name = mapping.get("graphiti_attribute")
        if isinstance(attr_name, str) and attr_name:
            datatype_property_to_attr[owl_prop] = attr_name

    return {
        "class_to_label": class_to_label,
        "object_property_to_edge": object_property_to_edge,
        "datatype_property_to_attr": datatype_property_to_attr,
    }
