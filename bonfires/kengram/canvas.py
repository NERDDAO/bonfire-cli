"""Export a kEngram manifest as an Obsidian .canvas file.

Layout: summary node at top center, entities in a grid below,
metadata group at bottom right. Deterministic from sorted node order.
"""

from __future__ import annotations

from typing import Any

from bonfires.kengram.manifest import KEngramManifest

NODE_W = 280
NODE_H = 100
GAP_X = 40
GAP_Y = 60
COLS = 3


def export_canvas(
    manifest: KEngramManifest,
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    episodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    canvas_nodes: list[dict[str, Any]] = []
    canvas_edges: list[dict[str, Any]] = []

    summary_text = f"# {manifest.name}\n{manifest.summary}" if manifest.summary else f"# {manifest.name}"
    canvas_nodes.append({
        "id": "summary",
        "type": "text",
        "x": 0,
        "y": -300,
        "width": 360,
        "height": 100,
        "color": "6",
        "text": summary_text,
    })

    sorted_entities = sorted(entities, key=lambda e: e.get("name", ""))
    pinned_set = set(manifest.pinned_nodes)

    rendered_idx = 0
    for ent in sorted_entities:
        uuid = ent.get("uuid", "")
        if uuid not in pinned_set:
            continue
        col = rendered_idx % COLS
        row = rendered_idx // COLS
        x = (col - 1) * (NODE_W + GAP_X)
        y = -100 + row * (NODE_H + GAP_Y)

        labels = ent.get("labels", [])
        label_str = " ".join(f"[{label}]" for label in labels) if labels else ""
        node_text = f"### {ent.get('name', uuid)}\n{label_str}\n{ent.get('summary', '')}"

        color = "4"
        if "TaxonomyLabel" in labels:
            color = "3"
        elif "Update" in labels:
            color = "5"

        canvas_nodes.append({
            "id": uuid,
            "type": "text",
            "x": x,
            "y": y,
            "width": NODE_W,
            "height": NODE_H,
            "color": color,
            "text": node_text.strip(),
        })
        rendered_idx += 1

    for j, edge in enumerate(edges):
        src = edge.get("source_node_uuid", "")
        tgt = edge.get("target_node_uuid", "")
        if src in pinned_set and tgt in pinned_set:
            canvas_edges.append({
                "id": f"e{j}",
                "fromNode": src,
                "fromSide": "bottom",
                "toNode": tgt,
                "toSide": "top",
                "label": edge.get("name", ""),
            })

    for ent in sorted_entities:
        uuid = ent.get("uuid", "")
        if uuid in pinned_set:
            canvas_edges.append({
                "id": f"s-{uuid}",
                "fromNode": "summary",
                "fromSide": "bottom",
                "toNode": uuid,
                "toSide": "top",
                "color": "6",
            })

    if episodes:
        sorted_eps = sorted(episodes, key=lambda e: e.get("created_at", e.get("valid_at", "")))
        ep_y = -100 + ((rendered_idx // COLS) + 1) * (NODE_H + GAP_Y) + GAP_Y
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

    meta_y = -100 + ((rendered_idx // COLS) + 2) * (NODE_H + GAP_Y)
    canvas_nodes.append({
        "id": "metadata",
        "type": "text",
        "x": NODE_W + GAP_X,
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
