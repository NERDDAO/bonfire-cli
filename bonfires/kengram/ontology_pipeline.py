"""OWL L2 translation pipeline — stateless functions for kEngram ↔ RDF translation.

Takes a KEngramManifest + composed OntologyProfile and produces RDF graphs,
constraint violations, and gap descriptors.  All functions are pure / stateless:
they accept data and return data without mutating globals or disk state.
"""

from __future__ import annotations

from typing import Any, Literal

from rdflib import RDF, Graph, Literal as RDFLiteral, Namespace, URIRef

from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.ontology_profile import KE_NAMESPACE_URI, OntologyProfile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KE = Namespace(KE_NAMESPACE_URI)

SerializationFormat = Literal["turtle", "json-ld", "xml", "n3", "nt"]

# ---------------------------------------------------------------------------
# Vocabulary extraction
# ---------------------------------------------------------------------------


def extract_vocabulary(manifest: KEngramManifest) -> dict[str, set[str]]:
    """Extract the distinct labels, edge names, and attribute keys present in *manifest*.

    Returns a dict with three ``set`` values:

    - ``labels`` — all entity labels found in ``_node_meta``
    - ``edge_names`` — all edge relation names parsed from ``pinned_edges``
    - ``attribute_keys`` — all attribute keys found across node meta summaries
      (name and summary are always included when present)
    """
    labels: set[str] = set()
    edge_names: set[str] = set()
    attribute_keys: set[str] = set()

    for meta in manifest._node_meta.values():
        for label in meta.get("labels", []):
            if label:
                labels.add(label)
        # name and summary are always treated as attribute keys when present
        if meta.get("name"):
            attribute_keys.add("name")
        if meta.get("summary"):
            attribute_keys.add("summary")
        # Any extra keys in meta beyond the known structural ones are attributes
        for key in meta:
            if key not in ("labels", "name", "summary"):
                attribute_keys.add(key)

    for edge_key in manifest.pinned_edges:
        parts = edge_key.split(":", 2)
        if len(parts) == 3:
            edge_names.add(parts[2])

    return {"labels": labels, "edge_names": edge_names, "attribute_keys": attribute_keys}


# ---------------------------------------------------------------------------
# Profile scoring
# ---------------------------------------------------------------------------


def score_profile(profile: OntologyProfile, vocabulary: dict[str, set[str]]) -> float:
    """Return the coverage ratio ``|mapped_terms| / |total_terms|``.

    Terms include labels, edge names, and attribute keys from *vocabulary*.
    A profile that maps none of them scores 0.0; one that maps all scores 1.0.
    Returns 0.0 when the total vocabulary is empty.
    """
    total_terms: set[str] = (
        vocabulary.get("labels", set())
        | vocabulary.get("edge_names", set())
        | vocabulary.get("attribute_keys", set())
    )
    if not total_terms:
        return 0.0

    mapped: set[str] = set()
    for term in vocabulary.get("labels", set()):
        if term in profile.class_map:
            mapped.add(term)
    for term in vocabulary.get("edge_names", set()):
        if term in profile.object_property_map:
            mapped.add(term)
    for term in vocabulary.get("attribute_keys", set()):
        if term in profile.datatype_property_map:
            mapped.add(term)

    return len(mapped) / len(total_terms)


# ---------------------------------------------------------------------------
# Profile identification
# ---------------------------------------------------------------------------


def identify_profiles(
    vocabulary: dict[str, set[str]],
    available_profiles: list[OntologyProfile],
) -> list[tuple[OntologyProfile, float]]:
    """Score all *available_profiles* against *vocabulary* and return them sorted descending.

    Profiles with equal scores retain their original relative order (stable sort).
    """
    scored = [(profile, score_profile(profile, vocabulary)) for profile in available_profiles]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Namespace resolution helpers
# ---------------------------------------------------------------------------


def _resolve_prefixed(term: str, namespaces: dict[str, str]) -> URIRef:
    """Expand a ``prefix:local`` CURIE to a full URI using *namespaces*.

    Falls back to the kEngram namespace when the prefix is not registered.
    Absolute IRIs (starting with ``http`` or ``https``) are returned as-is.
    """
    if term.startswith("http://") or term.startswith("https://"):
        return URIRef(term)
    if ":" in term:
        prefix, local = term.split(":", 1)
        base = namespaces.get(prefix)
        if base:
            return URIRef(base + local)
    # Unmapped — fall back to ke: namespace
    return _KE[term]


def _bind_namespaces(graph: Graph, namespaces: dict[str, str]) -> None:
    """Bind all profile namespaces plus the base ke: namespace onto *graph*."""
    for prefix, uri in namespaces.items():
        graph.bind(prefix, Namespace(uri))
    graph.bind("ke", _KE)
    graph.bind("rdf", RDF)


# ---------------------------------------------------------------------------
# L1 → RDF translation
# ---------------------------------------------------------------------------


def parse_to_rdf(manifest: KEngramManifest, composed_profile: OntologyProfile) -> Graph:
    """Translate a kEngram manifest to an RDF graph deterministically.

    Entity URIs follow the pattern ``kengram:{kengram_id}/entity/{uuid}``.
    Labels are mapped to ``rdf:type`` triples via ``class_map``.
    Attributes are mapped via ``datatype_property_map``; unmapped keys fall back
    to the ``ke:`` namespace.
    Edges are mapped via ``object_property_map``; unmapped relation names fall
    back to the ``ke:`` namespace.
    """
    graph = Graph()
    _bind_namespaces(graph, composed_profile.namespaces)

    ns = composed_profile.namespaces
    kengram_base = f"http://bonfires.ai/kengram/{manifest.id}/"
    KENGRAM = Namespace(kengram_base)
    graph.bind("kengram", KENGRAM)

    # Build entity URI map: uuid → URIRef
    entity_uris: dict[str, URIRef] = {}
    for uuid in manifest.pinned_nodes:
        entity_uris[uuid] = KENGRAM[f"entity/{uuid}"]

    # --- Entities: types and attributes ---
    for uuid, meta in manifest._node_meta.items():
        if uuid not in entity_uris:
            continue
        subject = entity_uris[uuid]

        # rdf:type assertions from labels via class_map
        for label in meta.get("labels", []):
            mapping = composed_profile.class_map.get(label)
            if mapping:
                owl_class_str = mapping.get("owl_class")
                if isinstance(owl_class_str, str) and owl_class_str:
                    graph.add((subject, RDF.type, _resolve_prefixed(owl_class_str, ns)))
            else:
                # Unmapped label → ke: fallback type
                graph.add((subject, RDF.type, _KE[label]))

        # Datatype property assertions for name and summary
        for attr_key in ("name", "summary"):
            value = meta.get(attr_key)
            if not value:
                continue
            mapping = composed_profile.datatype_property_map.get(attr_key)
            if mapping:
                owl_prop_str = mapping.get("owl_property")
                if isinstance(owl_prop_str, str) and owl_prop_str:
                    prop = _resolve_prefixed(owl_prop_str, ns)
                    graph.add((subject, prop, RDFLiteral(str(value))))
                    continue
            # Unmapped → ke: fallback
            graph.add((subject, _KE[attr_key], RDFLiteral(str(value))))

        # Any extra attributes beyond known structural keys
        for attr_key, value in meta.items():
            if attr_key in ("labels", "name", "summary"):
                continue
            if value is None:
                continue
            mapping = composed_profile.datatype_property_map.get(attr_key)
            if mapping:
                owl_prop_str = mapping.get("owl_property")
                if isinstance(owl_prop_str, str) and owl_prop_str:
                    prop = _resolve_prefixed(owl_prop_str, ns)
                    graph.add((subject, prop, RDFLiteral(str(value))))
                    continue
            graph.add((subject, _KE[attr_key], RDFLiteral(str(value))))

    # --- Edges: object property assertions ---
    for edge_key in manifest.pinned_edges:
        parts = edge_key.split(":", 2)
        if len(parts) != 3:
            continue
        source_uuid, target_uuid, edge_name = parts
        source_uri = entity_uris.get(source_uuid)
        target_uri = entity_uris.get(target_uuid)
        if source_uri is None or target_uri is None:
            continue

        mapping = composed_profile.object_property_map.get(edge_name)
        if mapping:
            owl_prop_str = mapping.get("owl_property")
            if isinstance(owl_prop_str, str) and owl_prop_str:
                prop = _resolve_prefixed(owl_prop_str, ns)
                graph.add((source_uri, prop, target_uri))
                continue
        # Unmapped → ke: fallback
        graph.add((source_uri, _KE[edge_name], target_uri))

    return graph


# ---------------------------------------------------------------------------
# Constraint validation
# ---------------------------------------------------------------------------


def _get_entity_types(graph: Graph, subject: URIRef) -> set[str]:
    """Return the set of rdf:type URI strings for *subject* in *graph*."""
    return {str(obj) for obj in graph.objects(subject, RDF.type)}


def _has_property(graph: Graph, subject: URIRef, prop_uri: URIRef) -> bool:
    return (subject, prop_uri, None) in graph


def _count_property(graph: Graph, subject: URIRef, prop_uri: URIRef) -> int:
    return sum(1 for _ in graph.objects(subject, prop_uri))



def validate_graph(
    manifest: KEngramManifest,
    composed_profile: OntologyProfile,
) -> list[dict[str, Any]]:
    """Check per-entity OWL constraints and return a list of violation dicts.

    Each violation has:
    - ``entity_uuid``
    - ``entity_name``
    - ``owl_class``
    - ``violation``  — machine-readable type string
    - ``property``   — OWL property IRI (or empty string)
    - ``message``    — human-readable description
    """
    graph = parse_to_rdf(manifest, composed_profile)
    ns = composed_profile.namespaces
    kengram_base = f"http://bonfires.ai/kengram/{manifest.id}/"
    KENGRAM = Namespace(kengram_base)

    violations: list[dict[str, Any]] = []

    for uuid, meta in manifest._node_meta.items():
        if uuid not in manifest.pinned_nodes:
            continue

        subject = KENGRAM[f"entity/{uuid}"]
        entity_name = str(meta.get("name", uuid))
        entity_labels: list[str] = meta.get("labels", [])

        for label in entity_labels:
            class_mapping = composed_profile.class_map.get(label)
            if not class_mapping:
                continue

            owl_class = str(class_mapping.get("owl_class", label))
            constraints: dict[str, Any] = class_mapping.get("constraints", {})
            if not isinstance(constraints, dict):
                continue

            # --- required_properties ---
            required: list[str] = constraints.get("required_properties", [])
            for req_prop_str in required:
                req_prop_uri = _resolve_prefixed(req_prop_str, ns)
                if not _has_property(graph, subject, req_prop_uri):
                    violations.append(
                        {
                            "entity_uuid": uuid,
                            "entity_name": entity_name,
                            "owl_class": owl_class,
                            "violation": "missing_required_property",
                            "property": req_prop_str,
                            "message": (
                                f"Required property '{req_prop_str}' is absent on "
                                f"'{entity_name}' (class {owl_class})."
                            ),
                        }
                    )

            # --- cardinality restrictions and allValuesFrom / someValuesFrom ---
            restrictions: list[dict[str, Any]] = constraints.get("restrictions", [])
            for restriction in restrictions:
                if not isinstance(restriction, dict):
                    continue
                prop_str: str = restriction.get("property", "")
                if not prop_str:
                    continue
                prop_uri = _resolve_prefixed(prop_str, ns)
                restriction_type: str = restriction.get("type", "")
                target_str: str = restriction.get("target", "")

                if restriction_type == "minCardinality":
                    min_card = int(restriction.get("value", 1))
                    count = _count_property(graph, subject, prop_uri)
                    if count < min_card:
                        violations.append(
                            {
                                "entity_uuid": uuid,
                                "entity_name": entity_name,
                                "owl_class": owl_class,
                                "violation": "cardinality_min",
                                "property": prop_str,
                                "message": (
                                    f"'{entity_name}' has {count} value(s) for "
                                    f"'{prop_str}'; minimum cardinality is {min_card}."
                                ),
                            }
                        )

                elif restriction_type == "maxCardinality":
                    max_card = int(restriction.get("value", 1))
                    count = _count_property(graph, subject, prop_uri)
                    if count > max_card:
                        violations.append(
                            {
                                "entity_uuid": uuid,
                                "entity_name": entity_name,
                                "owl_class": owl_class,
                                "violation": "cardinality_max",
                                "property": prop_str,
                                "message": (
                                    f"'{entity_name}' has {count} value(s) for "
                                    f"'{prop_str}'; maximum cardinality is {max_card}."
                                ),
                            }
                        )

                elif restriction_type == "exactCardinality":
                    exact_card = int(restriction.get("value", 1))
                    count = _count_property(graph, subject, prop_uri)
                    if count != exact_card:
                        violations.append(
                            {
                                "entity_uuid": uuid,
                                "entity_name": entity_name,
                                "owl_class": owl_class,
                                "violation": "cardinality_exact",
                                "property": prop_str,
                                "message": (
                                    f"'{entity_name}' has {count} value(s) for "
                                    f"'{prop_str}'; expected exactly {exact_card}."
                                ),
                            }
                        )

                elif restriction_type == "allValuesFrom" and target_str:
                    # OWL open-world: only warn when we can inspect types
                    target_uri = _resolve_prefixed(target_str, ns)
                    for obj in graph.objects(subject, prop_uri):
                        if not isinstance(obj, URIRef):
                            continue
                        obj_types = _get_entity_types(graph, obj)
                        if str(target_uri) not in obj_types:
                            violations.append(
                                {
                                    "entity_uuid": uuid,
                                    "entity_name": entity_name,
                                    "owl_class": owl_class,
                                    "violation": "allValuesFrom_mismatch",
                                    "property": prop_str,
                                    "message": (
                                        f"owl:allValuesFrom {target_str}: object of "
                                        f"'{entity_name}' via '{prop_str}' is not typed "
                                        f"as '{target_str}' (open-world warning)."
                                    ),
                                }
                            )

                elif restriction_type == "someValuesFrom" and target_str:
                    target_uri = _resolve_prefixed(target_str, ns)
                    found = any(
                        isinstance(obj, URIRef)
                        and str(target_uri) in _get_entity_types(graph, obj)
                        for obj in graph.objects(subject, prop_uri)
                    )
                    if not found:
                        violations.append(
                            {
                                "entity_uuid": uuid,
                                "entity_name": entity_name,
                                "owl_class": owl_class,
                                "violation": "someValuesFrom_missing",
                                "property": prop_str,
                                "message": (
                                    f"owl:someValuesFrom {target_str}: '{entity_name}' "
                                    f"has no object typed as '{target_str}' via "
                                    f"'{prop_str}' (open-world warning)."
                                ),
                            }
                        )

            # --- Edge domain / range warnings (open-world) ---
            for _edge_name, prop_mapping in composed_profile.object_property_map.items():
                if not isinstance(prop_mapping, dict):
                    continue
                domain_str: str = prop_mapping.get("domain", "")
                range_str: str = prop_mapping.get("range", "")
                owl_prop_str: str = prop_mapping.get("owl_property", "")
                if not owl_prop_str:
                    continue
                owl_prop_uri = _resolve_prefixed(owl_prop_str, ns)

                entity_type_uris = _get_entity_types(graph, subject)

                if domain_str and (subject, owl_prop_uri, None) in graph:
                    domain_uri = str(_resolve_prefixed(domain_str, ns))
                    if domain_uri not in entity_type_uris:
                        violations.append(
                            {
                                "entity_uuid": uuid,
                                "entity_name": entity_name,
                                "owl_class": owl_class,
                                "violation": "domain_mismatch",
                                "property": owl_prop_str,
                                "message": (
                                    f"'{entity_name}' uses property '{owl_prop_str}' "
                                    f"but is not typed as its declared domain '{domain_str}' "
                                    f"(open-world warning)."
                                ),
                            }
                        )

                if range_str:
                    range_uri_str = str(_resolve_prefixed(range_str, ns))
                    for obj in graph.objects(subject, owl_prop_uri):
                        if not isinstance(obj, URIRef):
                            continue
                        obj_type_uris = _get_entity_types(graph, obj)
                        if range_uri_str not in obj_type_uris:
                            violations.append(
                                {
                                    "entity_uuid": uuid,
                                    "entity_name": entity_name,
                                    "owl_class": owl_class,
                                    "violation": "range_mismatch",
                                    "property": owl_prop_str,
                                    "message": (
                                        f"An object of '{entity_name}' via "
                                        f"'{owl_prop_str}' is not typed as its declared "
                                        f"range '{range_str}' (open-world warning)."
                                    ),
                                }
                            )

    return violations


# ---------------------------------------------------------------------------
# Manifest annotation
# ---------------------------------------------------------------------------


def annotate_manifest(
    manifest: KEngramManifest,
    composed_profile: OntologyProfile,
    violations: list[dict[str, Any]],
) -> None:
    """Write per-entity per-profile results into ``manifest.ontology_annotations``.

    Builds a per-entity violation index from *violations*, then calls
    ``manifest.annotate_entity`` for every pinned node.
    """
    ns = composed_profile.namespaces

    # Build violation index: uuid → [violation_message, ...]
    violation_index: dict[str, list[str]] = {}
    for v in violations:
        uid: str = v["entity_uuid"]
        violation_index.setdefault(uid, []).append(v["message"])

    for uuid, meta in manifest._node_meta.items():
        if uuid not in manifest.pinned_nodes:
            continue

        entity_labels: list[str] = meta.get("labels", [])

        # Collect rdf:type URIs from class_map
        rdf_types: list[str] = []
        for label in entity_labels:
            mapping = composed_profile.class_map.get(label)
            if mapping:
                owl_class_str = mapping.get("owl_class")
                if isinstance(owl_class_str, str) and owl_class_str:
                    rdf_types.append(str(_resolve_prefixed(owl_class_str, ns)))
            else:
                rdf_types.append(str(_KE[label]))

        # Collect mapped property IRIs from name/summary attributes
        mapped_properties: dict[str, Any] = {}
        for attr_key in ("name", "summary"):
            value = meta.get(attr_key)
            if not value:
                continue
            prop_mapping = composed_profile.datatype_property_map.get(attr_key)
            if prop_mapping:
                owl_prop_str = prop_mapping.get("owl_property")
                if isinstance(owl_prop_str, str) and owl_prop_str:
                    prop_uri = str(_resolve_prefixed(owl_prop_str, ns))
                    mapped_properties[prop_uri] = str(value)
                    continue
            mapped_properties[str(_KE[attr_key])] = str(value)

        entity_violations = violation_index.get(uuid, [])

        manifest.annotate_entity(
            uuid=uuid,
            profile_id=composed_profile.id,
            rdf_types=rdf_types,
            mapped_properties=mapped_properties,
            violations=entity_violations,
        )


# ---------------------------------------------------------------------------
# RDF export
# ---------------------------------------------------------------------------


def export_rdf(graph: Graph, serialization: SerializationFormat = "turtle") -> str:
    """Serialize *graph* to a string in the requested format.

    Supported formats: ``turtle``, ``json-ld``, ``xml``, ``n3``, ``nt``.
    """
    return graph.serialize(format=serialization)


# ---------------------------------------------------------------------------
# Gap extraction
# ---------------------------------------------------------------------------


def extract_gaps(manifest: KEngramManifest) -> list[dict[str, Any]]:
    """Build structured gap descriptors from ``ontology_annotations`` violations.

    Iterates over all annotated entities and expands each violation string into
    a gap descriptor dict with entity context, the missing element, and ontology
    context about what kind of data is expected.

    Gap descriptor keys:
    - ``entity_uuid``
    - ``entity_name``
    - ``owl_class``
    - ``gap_type``
    - ``property``
    - ``property_description``
    - ``expected_type``
    - ``context``
    """
    gaps: list[dict[str, Any]] = []

    for uuid, annotation in manifest.ontology_annotations.items():
        entity_violations: list[str] = annotation.get("violations", [])
        if not entity_violations:
            continue

        rdf_types: list[str] = annotation.get("rdf_types", [])
        owl_class = rdf_types[0] if rdf_types else ""

        meta = manifest._node_meta.get(uuid, {})
        entity_name = str(meta.get("name", uuid))
        entity_labels: list[str] = meta.get("labels", [])
        existing_attrs = [k for k in meta if k not in ("labels",)]

        # Build a short context sentence describing what the entity has
        context_parts: list[str] = []
        if entity_labels:
            context_parts.append(f"Labels: {', '.join(entity_labels)}")
        if existing_attrs:
            context_parts.append(f"has attributes: {', '.join(existing_attrs)}")
        context = "; ".join(context_parts) if context_parts else "No additional context"

        for violation_message in entity_violations:
            gap = _parse_violation_to_gap(
                uuid=uuid,
                entity_name=entity_name,
                owl_class=owl_class,
                violation_message=violation_message,
                context=context,
            )
            gaps.append(gap)

    return gaps


def _parse_violation_to_gap(
    uuid: str,
    entity_name: str,
    owl_class: str,
    violation_message: str,
    context: str,
) -> dict[str, Any]:
    """Derive a gap descriptor from a single violation message string.

    Heuristically extracts the property name, gap type, and expected type
    from the message text.  The message format is produced by ``validate_graph``.
    """
    gap_type = "constraint_violation"
    prop = ""
    property_description = violation_message
    expected_type = ""

    lower = violation_message.lower()

    if "required property" in lower and "absent" in lower:
        gap_type = "missing_required_property"
        # Extract quoted property name
        parts = violation_message.split("'")
        if len(parts) >= 2:
            prop = parts[1]
        property_description = f"Required OWL property '{prop}' is missing"
        expected_type = _infer_expected_type(prop)

    elif "minimum cardinality" in lower:
        gap_type = "cardinality_min"
        parts = violation_message.split("'")
        if len(parts) >= 4:
            prop = parts[3]
        property_description = f"Too few values for property '{prop}'"
        expected_type = _infer_expected_type(prop)

    elif "maximum cardinality" in lower:
        gap_type = "cardinality_max"
        parts = violation_message.split("'")
        if len(parts) >= 4:
            prop = parts[3]
        property_description = f"Too many values for property '{prop}'"
        expected_type = _infer_expected_type(prop)

    elif "allvaluesfrom" in lower:
        gap_type = "allValuesFrom_mismatch"
        parts = violation_message.split("'")
        if len(parts) >= 4:
            prop = parts[3]
        property_description = f"Object of '{prop}' has unexpected type"
        # Target type follows "allValuesFrom"
        idx = violation_message.find("allValuesFrom")
        if idx != -1:
            expected_type = violation_message[idx + len("allValuesFrom"):].strip().split()[0]

    elif "somevaluesfrom" in lower:
        gap_type = "someValuesFrom_missing"
        parts = violation_message.split("'")
        if len(parts) >= 2:
            prop = parts[1]
        property_description = f"No object of required type via property '{prop}'"
        idx = violation_message.find("someValuesFrom")
        if idx != -1:
            expected_type = violation_message[idx + len("someValuesFrom"):].strip().split()[0]

    elif "domain_mismatch" in lower or "declared domain" in lower:
        gap_type = "domain_mismatch"
        parts = violation_message.split("'")
        if len(parts) >= 4:
            prop = parts[3]
        property_description = f"Entity type does not match domain of '{prop}'"

    elif "range_mismatch" in lower or "declared range" in lower:
        gap_type = "range_mismatch"
        parts = violation_message.split("'")
        if len(parts) >= 4:
            prop = parts[3]
        property_description = f"Object type does not match range of '{prop}'"
        expected_type = _infer_expected_type(prop)

    return {
        "entity_uuid": uuid,
        "entity_name": entity_name,
        "owl_class": owl_class,
        "gap_type": gap_type,
        "property": prop,
        "property_description": property_description,
        "expected_type": expected_type,
        "context": context,
    }


def _infer_expected_type(prop_str: str) -> str:
    """Make a best-effort guess at the expected data type from a property IRI.

    Returns an empty string when no useful inference is possible.
    """
    lower = prop_str.lower()
    if any(k in lower for k in ("label", "name", "title", "comment", "description")):
        return "xsd:string"
    if any(k in lower for k in ("date", "time", "created", "modified", "born", "died")):
        return "xsd:dateTime"
    if any(k in lower for k in ("count", "age", "number", "cardinality")):
        return "xsd:integer"
    if any(k in lower for k in ("weight", "height", "measure", "quantity", "value")):
        return "xsd:decimal"
    if any(k in lower for k in ("uri", "url", "iri", "link", "homepage")):
        return "xsd:anyURI"
    return ""
