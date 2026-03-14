"""Export a kEngram manifest as an Obsidian .canvas file.

Layout: topology-aware hierarchical layout based on edge relationships.
Nodes are assigned to layers by graph depth from root nodes (those with
no incoming edges). Within each layer, nodes are spread horizontally.
Edge sides (fromSide/toSide) are chosen based on relative positions.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from bonfires.kengram.manifest import KEngramManifest

NODE_W = 300
NODE_H = 130
GAP_X = 60
GAP_Y = 80


def _assign_layers(
    node_ids: list[str],
    edges: list[dict[str, Any]],
) -> dict[str, int]:
    """Assign each node to a layer using BFS from root nodes.

    Roots are nodes with no incoming edges. If every node has incoming
    edges (a cycle), pick the node with the most outgoing edges as root.
    """
    children: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, int] = defaultdict(int)
    node_set = set(node_ids)

    for edge in edges:
        src = edge.get("source_node_uuid", "")
        tgt = edge.get("target_node_uuid", "")
        if src in node_set and tgt in node_set:
            children[src].append(tgt)
            incoming[tgt] = incoming.get(tgt, 0) + 1

    if not node_ids:
        return {}

    # Find roots: nodes with zero incoming edges
    roots = [n for n in node_ids if incoming.get(n, 0) == 0]

    if not roots:
        # Cycle: pick node with most outgoing edges
        out_count = defaultdict(int)
        for edge in edges:
            src = edge.get("source_node_uuid", "")
            if src in node_set:
                out_count[src] += 1
        roots = [max(node_ids, key=lambda n: out_count.get(n, 0))]

    # BFS to assign layers
    layers: dict[str, int] = {}
    queue: deque[str] = deque()
    for root in roots:
        if root not in layers:
            layers[root] = 0
            queue.append(root)

    while queue:
        node = queue.popleft()
        for child in children.get(node, []):
            if child not in layers:
                layers[child] = layers[node] + 1
                queue.append(child)

    # Assign remaining disconnected nodes to last layer + 1
    max_layer = max(layers.values()) if layers else 0
    for n in node_ids:
        if n not in layers:
            layers[n] = max_layer + 1

    return layers


def _pick_sides(
    from_x: float, from_y: float, to_x: float, to_y: float,
) -> tuple[str, str]:
    """Choose edge attachment sides based on relative node positions."""
    dx = to_x - from_x
    dy = to_y - from_y

    if abs(dy) > abs(dx):
        # Primarily vertical
        if dy > 0:
            return "bottom", "top"
        return "top", "bottom"
    # Primarily horizontal
    if dx > 0:
        return "right", "left"
    return "left", "right"


def export_canvas(
    manifest: KEngramManifest,
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    episodes: list[dict[str, Any]] | None = None,
    node_status: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Export manifest to Obsidian canvas.

    node_status maps uuid -> "OK" | "DRIFT" | "NOT_IN_KG" | "UNVERIFIED".
    Colors are based on verify status:
      4 (green)  = verified, matches KG
      5 (cyan)   = unverified (not checked yet)
      2 (orange) = local-only / not in KG
      1 (red)    = drift detected (KG differs)
      3 (yellow) = TaxonomyLabel (verified OK with taxonomy)
    """
    canvas_nodes: list[dict[str, Any]] = []
    canvas_edges: list[dict[str, Any]] = []
    pinned_set = set(manifest.pinned_nodes)

    # Filter to pinned entities
    pinned_entities = [e for e in entities if e.get("uuid", "") in pinned_set]
    pinned_edges = [
        e for e in edges
        if e.get("source_node_uuid", "") in pinned_set
        and e.get("target_node_uuid", "") in pinned_set
    ]

    # Build entity lookup
    entity_map = {e["uuid"]: e for e in pinned_entities}
    node_ids = [e["uuid"] for e in pinned_entities]

    # Assign layers based on edge topology
    layers = _assign_layers(node_ids, pinned_edges)

    # Group nodes by layer
    layer_groups: dict[int, list[str]] = defaultdict(list)
    for node_id, layer in sorted(layers.items(), key=lambda kv: kv[1]):
        layer_groups[layer].append(node_id)

    # Sort within each layer by name for determinism
    for layer in layer_groups:
        layer_groups[layer].sort(key=lambda uid: entity_map.get(uid, {}).get("name", uid))

    # Compute positions: each layer is a row, nodes spread horizontally
    positions: dict[str, tuple[float, float]] = {}
    max_layer = max(layer_groups.keys()) if layer_groups else 0

    for layer_idx in range(max_layer + 1):
        group = layer_groups.get(layer_idx, [])
        count = len(group)
        total_width = count * NODE_W + (count - 1) * GAP_X if count > 0 else 0
        start_x = -total_width / 2

        for i, node_id in enumerate(group):
            x = start_x + i * (NODE_W + GAP_X)
            y = layer_idx * (NODE_H + GAP_Y)
            positions[node_id] = (x, y)

    # Summary node above everything
    summary_text = f"# {manifest.name}\n{manifest.summary}" if manifest.summary else f"# {manifest.name}"
    summary_y = -NODE_H - GAP_Y - 40
    canvas_nodes.append({
        "id": "summary",
        "type": "text",
        "x": -220,
        "y": summary_y,
        "width": 440,
        "height": 120,
        "color": "6",
        "text": summary_text,
    })

    # Entity nodes
    for node_id in node_ids:
        ent = entity_map.get(node_id)
        if not ent:
            continue

        x, y = positions.get(node_id, (0, 0))
        labels = ent.get("labels", [])
        label_str = " ".join(f"[{label}]" for label in labels) if labels else ""
        node_text = f"### {ent.get('name', node_id)}\n{label_str}\n{ent.get('summary', '')}"

        # Color by verify status: 4=green(OK), 5=cyan(unverified), 2=orange(not in KG), 1=red(drift)
        status = (node_status or {}).get(node_id, "UNVERIFIED")
        if status == "OK":
            # Verified OK — green, or yellow for TaxonomyLabel
            color = "3" if "TaxonomyLabel" in labels else "4"
        elif status == "DRIFT":
            color = "1"  # red
        elif status == "NOT_IN_KG":
            color = "2"  # orange
        else:
            color = "5"  # cyan = unverified

        canvas_nodes.append({
            "id": node_id,
            "type": "text",
            "x": int(x),
            "y": int(y),
            "width": NODE_W,
            "height": NODE_H,
            "color": color,
            "text": node_text.strip(),
        })

    # Edges with topology-aware sides
    for j, edge in enumerate(pinned_edges):
        src = edge.get("source_node_uuid", "")
        tgt = edge.get("target_node_uuid", "")
        src_pos = positions.get(src)
        tgt_pos = positions.get(tgt)

        if src_pos and tgt_pos:
            from_side, to_side = _pick_sides(
                src_pos[0], src_pos[1], tgt_pos[0], tgt_pos[1],
            )
        else:
            from_side, to_side = "bottom", "top"

        canvas_edges.append({
            "id": f"e{j}",
            "fromNode": src,
            "fromSide": from_side,
            "toNode": tgt,
            "toSide": to_side,
            "label": edge.get("name", ""),
        })

    # Episodes
    if episodes:
        sorted_eps = sorted(episodes, key=lambda e: e.get("created_at", e.get("valid_at", "")))
        ep_y = (max_layer + 1) * (NODE_H + GAP_Y) + GAP_Y
        for k, ep in enumerate(sorted_eps):
            ep_x = (k - len(sorted_eps) // 2) * (NODE_W + GAP_X)
            ep_name = ep.get("name", "Episode")
            ep_date = (ep.get("valid_at") or ep.get("created_at", ""))[:10]
            canvas_nodes.append({
                "id": f"ep-{k}",
                "type": "text",
                "x": ep_x,
                "y": ep_y,
                "width": NODE_W,
                "height": 80,
                "color": "2",
                "text": f"### {ep_name}\n{ep_date}",
            })

    # Metadata node bottom-right
    meta_y = (max_layer + 2) * (NODE_H + GAP_Y)
    max_x = max((p[0] for p in positions.values()), default=0)
    canvas_nodes.append({
        "id": "metadata",
        "type": "text",
        "x": int(max_x),
        "y": meta_y,
        "width": 300,
        "height": 80,
        "color": "2",
        "text": (
            f"**{manifest.id}** ({manifest.kengram_type})\n"
            f"Merkle: `{manifest.merkle_root[:16]}...`\n"
            f"Updated: {manifest.updated_at[:10]}"
        ),
    })

    return {"nodes": canvas_nodes, "edges": canvas_edges}
