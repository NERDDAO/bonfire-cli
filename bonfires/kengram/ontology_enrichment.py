"""Ontology-aware pin enrichment for kEngram manifests.

Provides hooks that run after ``manifest.pin_node`` and ``manifest.pin_edge``
to annotate entities with OWL types and validate edge domain/range constraints.
"""

from __future__ import annotations

from typing import Any

from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.ontology_profile import OntologyProfile, compose_profiles


def enrich_on_pin(
    manifest: KEngramManifest,
    entity_uuid: str,
    profiles: list[OntologyProfile],
) -> dict[str, Any]:
    """Enrich a freshly pinned entity with OWL annotations.

    Steps:
    1. Compose *profiles* into a single merged profile.
    2. Derive ``rdf_types`` by looking up each entity label in ``class_map``.
    3. Auto-fill trivial 1:1 datatype property mappings where ``functional: true``
       and the attribute is present on the entity.
    4. Write the annotation to ``manifest.ontology_annotations`` via
       :meth:`~KEngramManifest.annotate_entity`.

    Returns a summary dict with keys ``rdf_types``, ``auto_filled``, and
    ``warnings``.
    """
    if not profiles:
        return {"rdf_types": [], "auto_filled": [], "warnings": []}

    composed = compose_profiles(profiles)

    node_meta = manifest._node_meta.get(entity_uuid, {})
    labels: list[str] = node_meta.get("labels", [])

    # --- rdf_types: map Graphiti labels → OWL classes ---
    rdf_types: list[str] = []
    for label in labels:
        mapping = composed.class_map.get(label)
        if mapping:
            owl_class = mapping.get("owl_class")
            if isinstance(owl_class, str) and owl_class:
                rdf_types.append(owl_class)

    # --- auto_filled: trivial functional datatype property mappings ---
    # Attributes available on the pinned entity (only name and summary for now).
    entity_attrs: dict[str, str] = {}
    name_val = node_meta.get("name")
    summary_val = node_meta.get("summary")
    if name_val:
        entity_attrs["name"] = name_val
    if summary_val:
        entity_attrs["summary"] = summary_val

    auto_filled: list[str] = []
    mapped_properties: dict[str, Any] = {}
    for attr_name, prop_mapping in composed.datatype_property_map.items():
        if not prop_mapping.get("functional", False):
            continue
        if attr_name not in entity_attrs:
            continue
        owl_property = prop_mapping.get("owl_property")
        if not isinstance(owl_property, str) or not owl_property:
            continue
        mapped_properties[attr_name] = {
            "owl_property": owl_property,
            "value": entity_attrs[attr_name],
        }
        auto_filled.append(attr_name)

    warnings: list[str] = []

    manifest.annotate_entity(
        uuid=entity_uuid,
        profile_id=composed.id,
        rdf_types=rdf_types,
        mapped_properties=mapped_properties,
        violations=[],
    )

    return {"rdf_types": rdf_types, "auto_filled": auto_filled, "warnings": warnings}


def validate_edge_pin(
    manifest: KEngramManifest,
    source_uuid: str,
    target_uuid: str,
    edge_name: str,
    composed: OntologyProfile,
) -> list[str]:
    """Check domain/range constraints for a pinned edge.

    Looks up *edge_name* in ``composed.object_property_map``.  If a ``domain``
    or ``range`` OWL class is declared, verifies that the source / target
    entity's RDF types (from ``manifest.ontology_annotations``) include that
    class.

    Returns a (possibly empty) list of human-readable warning strings.
    """
    warnings: list[str] = []

    prop_mapping = composed.object_property_map.get(edge_name)
    if not prop_mapping:
        return warnings

    domain_class: str | None = prop_mapping.get("domain")
    range_class: str | None = prop_mapping.get("range")

    def _rdf_types_for(uuid: str) -> list[str]:
        annotation = manifest.ontology_annotations.get(uuid, {})
        return annotation.get("rdf_types", [])

    if domain_class:
        source_types = _rdf_types_for(source_uuid)
        if domain_class not in source_types:
            warnings.append(
                f"Edge '{edge_name}': source {source_uuid[:12]} types {source_types!r}"
                f" do not include domain class '{domain_class}'"
            )

    if range_class:
        target_types = _rdf_types_for(target_uuid)
        if range_class not in target_types:
            warnings.append(
                f"Edge '{edge_name}': target {target_uuid[:12]} types {target_types!r}"
                f" do not include range class '{range_class}'"
            )

    return warnings
