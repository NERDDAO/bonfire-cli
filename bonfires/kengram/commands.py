"""CLI commands for kEngram management."""

from __future__ import annotations

import json
import re
import sys
import uuid as _uuid_mod
from typing import Any, NoReturn

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires.config import get_config
from bonfires.kengram import kg_client
from bonfires.kengram.canvas import export_canvas
from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage

console = Console()
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

_json_flag = click.option("--json", "output_json", is_flag=True, help="Output as JSON.")


def _json_error(msg: str) -> NoReturn:
    """Print a JSON error object and exit with code 1."""
    click.echo(json.dumps({"error": msg}))
    sys.exit(1)


def _get_storage() -> KEngramStorage:
    cfg = get_config()
    return KEngramStorage(cfg["vault_dir"])


def _get_active_manifest(
    store: KEngramStorage, *, json_mode: bool = False,
) -> KEngramManifest | None:
    active_id = store.get_active()
    if not active_id:
        msg = "No active kEngram. Run `bonfire kengram new` first."
        if json_mode:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return None
    manifest = store.load(active_id)
    if not manifest:
        msg = f"Active kEngram '{active_id}' not found."
        if json_mode:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return None
    return manifest


def _parse_canvas_card(text: str) -> dict[str, str | list[str]] | None:
    """Parse a canvas card's text into entity metadata. Returns None if not an entity card."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith("### "):
        return None
    name = lines[0][4:].strip()
    label_line = lines[1] if len(lines) > 1 else ""
    labels = [m.group(1) for m in re.finditer(r"\[([^\]]+)\]", label_line)]
    summary_start = 2 if labels else 1
    summary = "\n".join(lines[summary_start:]).strip()
    return {"name": name, "summary": summary, "labels": labels}


def _check_canvas_diff(
    manifest: KEngramManifest, vault_dir: str,
) -> dict[str, dict[str, Any]]:
    """Compare canvas card content against manifest node_meta.

    Returns a dict of uuid -> {"status": "canvas_modified", "changes": [...]}
    for nodes whose canvas content differs from the pinned manifest state.
    """
    import os

    canvas_path = os.path.join(vault_dir, "kengrams", "canvas", f"{manifest.id}.canvas")
    if not os.path.isfile(canvas_path):
        return {}

    try:
        with open(canvas_path) as f:
            canvas_data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    dirty: dict[str, dict[str, Any]] = {}
    for node in canvas_data.get("nodes", []):
        if node.get("type") != "text":
            continue
        node_id = node.get("id", "")
        if node_id not in manifest._node_hashes:
            continue
        parsed = _parse_canvas_card(node.get("text", ""))
        if parsed is None:
            continue

        meta = manifest._node_meta.get(node_id, {})
        changes: list[str] = []
        if parsed["name"] != meta.get("name", ""):
            changes.append(f"name: '{meta.get('name', '')}' -> '{parsed['name']}'")
        if parsed["summary"] != meta.get("summary", ""):
            changes.append("summary changed")
        meta_labels = sorted(meta.get("labels", []))
        canvas_labels = sorted(parsed["labels"])
        if meta_labels != canvas_labels:
            changes.append(f"labels: {meta_labels} -> {canvas_labels}")
        if changes:
            dirty[node_id] = {"status": "canvas_modified", "changes": changes}

    return dirty


def _verify_for_export(manifest: KEngramManifest) -> dict[str, str]:
    """Run a quick verify and return per-node status for canvas coloring.

    Returns a dict of uuid -> "OK" | "DRIFT" | "NOT_IN_KG".
    On API failure, returns empty dict (all nodes will be "UNVERIFIED").
    """
    from bonfires.kengram.hashing import hash_node

    if not manifest.pinned_nodes:
        return {}

    cfg = get_config()
    fetched = kg_client.fetch_entities_batch(cfg, manifest.pinned_nodes)
    if fetched is None:
        return {}

    entity_map: dict[str, dict[str, Any]] = {str(e["uuid"]): e for e in fetched}
    status: dict[str, str] = {}

    for node_uuid in manifest.pinned_nodes:
        entity = entity_map.get(node_uuid)
        if entity is None:
            status[node_uuid] = "NOT_IN_KG"
            continue
        kg_hash = hash_node(
            node_uuid,
            str(entity.get("name", "")),
            str(entity.get("summary", "")),
            list(entity.get("labels", [])),
        )
        stored_hash = manifest._node_hashes.get(node_uuid, "")
        status[node_uuid] = "OK" if kg_hash == stored_hash else "DRIFT"

    return status


@click.group()
def kengram():
    """Manage kEngrams — verifiable knowledge subgraphs."""


@kengram.command()
@click.argument("name")
@click.option("--type", "kengram_type", default="session", type=click.Choice(["session", "topic"]))
@click.option("--parent", default=None, help="Parent topic kEngram ID.")
@_json_flag
def new(name: str, kengram_type: str, parent: str | None, output_json: bool):
    """Create a new kEngram."""
    cfg = get_config()
    store = _get_storage()
    manifest = KEngramManifest.create(
        name=name, kengram_type=kengram_type, group_id=cfg["group_id"], parent_topic=parent,
    )
    path = store.save(manifest)
    store.set_active(manifest.id)
    if output_json:
        click.echo(json.dumps({
            "status": "created",
            "id": manifest.id,
            "name": manifest.name,
            "type": manifest.kengram_type,
            "group_id": manifest.group_id,
            "path": str(path),
        }))
        return
    console.print(Panel(
        f"[bold green]Created[/bold green] {manifest.id}\n\n"
        f"  Name: {manifest.name}\n"
        f"  Type: {manifest.kengram_type}\n"
        f"  Group: {manifest.group_id}\n"
        f"  Manifest: {path}",
        title="kEngram", border_style="green",
    ))


@kengram.command()
@click.argument("uuid", required=False, default=None)
@click.option("--to", "target_id", default=None, help="Target kEngram ID (default: active).")
@click.option("--name", "node_name", default="", help="Entity name.")
@click.option("--summary", default="", help="Entity summary.")
@click.option("--labels", default="", help="Comma-separated labels.")
@click.option("--search", "search_query", default=None, help="Search KG for entities to pin.")
@_json_flag
def pin(
    uuid: str | None,
    target_id: str | None,
    node_name: str,
    summary: str,
    labels: str,
    search_query: str | None,
    output_json: bool,
):
    """Pin a KG entity to a kEngram."""
    cfg = get_config()
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            msg = f"kEngram '{target_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return

    if search_query:
        results = kg_client.search_entities(cfg, search_query)
        if not results:
            msg = "No results found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return

        if output_json:
            click.echo(json.dumps({
                "status": "search_results",
                "results": results,
            }))
            return

        table = Table(title="Search Results", title_style="bold")
        table.add_column("#", justify="right")
        table.add_column("UUID", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Labels")
        table.add_column("Summary")
        for i, entity in enumerate(results, 1):
            entity_summary = entity.get("summary", "") or ""
            truncated = entity_summary[:60] + "..." if len(entity_summary) > 60 else entity_summary
            table.add_row(
                str(i),
                entity.get("uuid", ""),
                entity.get("name", ""),
                ", ".join(entity.get("labels", [])),
                truncated,
            )
        console.print(table)
        choice = click.prompt("Select entity", type=int)
        if choice < 1 or choice > len(results):
            console.print("[red]Invalid selection.[/red]")
            return
        selected = results[choice - 1]
        pin_uuid = selected.get("uuid", "")
        pin_name = selected.get("name", "")
        pin_summary = selected.get("summary", "")
        pin_labels = selected.get("labels", [])
    elif uuid:
        pin_uuid = uuid
        if node_name:
            # Manual metadata provided — skip API call
            pin_name = node_name
            pin_summary = summary
            pin_labels = [lb.strip() for lb in labels.split(",") if lb.strip()] if labels else []
        else:
            # Try to fetch from KG
            entity = kg_client.fetch_entity(cfg, uuid)
            if entity:
                pin_name = entity.get("name", "")
                pin_summary = entity.get("summary", "")
                pin_labels = entity.get("labels", [])
            else:
                if output_json:
                    # In JSON mode, still proceed but with empty metadata
                    pass
                else:
                    console.print(
                        "[yellow]Warning:[/yellow] Could not fetch entity from KG, using provided metadata."
                    )
                pin_name = node_name
                pin_summary = summary
                pin_labels = [lb.strip() for lb in labels.split(",") if lb.strip()] if labels else []
    else:
        msg = "Provide a UUID or use --search."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    manifest.pin_node(uuid=pin_uuid, name=pin_name, summary=pin_summary, labels=pin_labels)
    store.save(manifest)
    if output_json:
        click.echo(json.dumps({
            "status": "pinned",
            "uuid": pin_uuid,
            "kengram_id": manifest.id,
            "merkle_root": manifest.merkle_root,
        }))
        return
    console.print(f"[green]Pinned[/green] {pin_uuid} to {manifest.id}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.argument("uuid")
@click.option("--from", "source_id", default=None, help="Source kEngram ID (default: active).")
@_json_flag
def unpin(uuid: str, source_id: str | None, output_json: bool):
    """Remove a node from a kEngram."""
    store = _get_storage()
    if source_id:
        manifest = store.load(source_id)
        if not manifest:
            msg = f"kEngram '{source_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return
    manifest.unpin_node(uuid)
    store.save(manifest)
    if output_json:
        click.echo(json.dumps({
            "status": "unpinned",
            "uuid": uuid,
            "kengram_id": manifest.id,
        }))
        return
    console.print(f"[yellow]Unpinned[/yellow] {uuid} from {manifest.id}")


@kengram.command()
@click.argument("source")
@click.argument("target")
@click.option("--name", "edge_name", required=True, help="Relationship name (e.g. USES, PRODUCES).")
@click.option("--fact", default="", help="Relationship description.")
@click.option("--local", "local_only", is_flag=True, help="Skip KG sync, pin locally only.")
@_json_flag
def edge(source: str, target: str, edge_name: str, fact: str, local_only: bool, output_json: bool):
    """Add an edge between two pinned nodes."""
    store = _get_storage()
    manifest = _get_active_manifest(store, json_mode=output_json)
    if not manifest:
        return
    if source not in manifest.pinned_nodes:
        msg = f"Source '{source}' is not pinned."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    if target not in manifest.pinned_nodes:
        msg = f"Target '{target}' is not pinned."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    # Push edge to canonical KG by UUID (unless --local)
    kg_synced = False
    if not local_only:
        cfg = get_config()
        result = kg_client.create_edge(cfg, source, target, edge_name, fact)
        kg_synced = result is not None
        if not output_json:
            if result:
                console.print("[green]Pushed[/green] edge to canonical KG")
            else:
                console.print("[yellow]Warning:[/yellow] Could not push edge to KG, pinning locally only.")

    manifest.pin_edge(source_uuid=source, target_uuid=target, name=edge_name, fact=fact)
    store.save(manifest)
    if output_json:
        click.echo(json.dumps({
            "status": "edge_created",
            "source": source,
            "target": target,
            "name": edge_name,
            "merkle_root": manifest.merkle_root,
            "kg_synced": kg_synced,
        }))
        return
    console.print(f"[green]Edge[/green] {source[:12]} —[{edge_name}]→ {target[:12]}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


def _resolve_name(
    name: str, name_to_uuid: dict[str, str], manifest: KEngramManifest,
) -> str | None:
    """Resolve a node name or UUID-like string to a UUID."""
    # 1. Check newly added nodes
    if name in name_to_uuid:
        return name_to_uuid[name]
    # 2. Check existing manifest node_meta by name
    for node_uuid, meta in manifest._node_meta.items():
        if meta.get("name") == name:
            return node_uuid
    # 3. If it's a valid UUID, use as-is
    if _UUID_RE.match(name):
        return name
    return None


@kengram.command()
@click.argument("file", required=False, default=None)
@click.option("--to", "target_id", default=None, help="Target kEngram ID (default: active).")
@click.option("--canvas", is_flag=True, help="Export canvas after applying batch.")
@click.option("--sync", is_flag=True, help="Push edges to canonical KG.")
@_json_flag
def batch(
    file: str | None,
    target_id: str | None,
    canvas: bool,
    sync: bool,
    output_json: bool,
):
    """Apply a changeset of nodes and edges from a JSON file (or stdin with -)."""
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            msg = f"kEngram '{target_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return

    # Read changeset JSON
    if file and file != "-":
        try:
            with open(file) as f:
                changeset = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"Failed to read changeset: {exc}"
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        raw = sys.stdin.read()
        try:
            changeset = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"Invalid JSON from stdin: {exc}"
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return

    nodes = changeset.get("nodes", [])
    edges = changeset.get("edges", [])

    manifest.begin_batch()

    # --- Nodes ---
    name_to_uuid: dict[str, str] = {}
    generated_uuids: dict[str, str] = {}
    nodes_added = 0
    for node in nodes:
        node_uuid = node.get("uuid", "auto")
        if node_uuid == "auto":
            node_uuid = str(_uuid_mod.uuid4())
            generated_uuids[node["name"]] = node_uuid
        node_name = node.get("name", "")
        node_summary = node.get("summary", "")
        node_labels = node.get("labels", [])
        manifest.pin_node(uuid=node_uuid, name=node_name, summary=node_summary, labels=node_labels)
        name_to_uuid[node_name] = node_uuid
        nodes_added += 1

    # --- Edges ---
    edges_added = 0
    edge_errors: list[str] = []
    for edge_item in edges:
        src = _resolve_name(edge_item["source"], name_to_uuid, manifest)
        tgt = _resolve_name(edge_item["target"], name_to_uuid, manifest)
        if not src or not tgt:
            err = f"Cannot resolve edge: {edge_item['source']} -> {edge_item['target']}"
            edge_errors.append(err)
            continue
        manifest.pin_edge(
            source_uuid=src,
            target_uuid=tgt,
            name=edge_item.get("name", "RELATED_TO"),
            fact=edge_item.get("fact", ""),
        )
        edges_added += 1

    if edge_errors:
        manifest.end_batch()
        msg = "Unresolvable edges: " + "; ".join(edge_errors)
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    manifest.end_batch()
    store.save(manifest)

    # --- Canvas export ---
    if canvas:
        entities = []
        for node_uuid in manifest.pinned_nodes:
            meta = manifest._node_meta.get(node_uuid, {})
            entities.append({
                "uuid": node_uuid,
                "name": meta.get("name", node_uuid[:12]),
                "summary": meta.get("summary", ""),
                "labels": meta.get("labels", []),
            })
        canvas_edges = []
        for key in manifest.pinned_edges:
            parts = key.split(":", 2)
            if len(parts) == 3:
                canvas_edges.append({
                    "source_node_uuid": parts[0],
                    "target_node_uuid": parts[1],
                    "name": parts[2],
                    "fact": "",
                })
        canvas_data = export_canvas(manifest, entities=entities, edges=canvas_edges)
        store.save_canvas(manifest.id, canvas_data)

    # --- KG sync ---
    if sync:
        cfg = get_config()
        for edge_item in edges:
            src = _resolve_name(edge_item["source"], name_to_uuid, manifest)
            tgt = _resolve_name(edge_item["target"], name_to_uuid, manifest)
            if src and tgt:
                try:
                    kg_client.create_edge(
                        cfg, src, tgt,
                        edge_item.get("name", "RELATED_TO"),
                        edge_item.get("fact", ""),
                    )
                except Exception:
                    pass

    # --- Output ---
    if output_json:
        click.echo(json.dumps({
            "status": "batch_applied",
            "kengram_id": manifest.id,
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "generated_uuids": generated_uuids,
            "merkle_root": manifest.merkle_root,
        }))
        return

    console.print(f"[green]Batch applied[/green] to {manifest.id}")
    console.print(f"  Nodes added: {nodes_added}")
    console.print(f"  Edges added: {edges_added}")
    if generated_uuids:
        console.print("  [bold]Generated UUIDs:[/bold]")
        for name_val, uuid_val in generated_uuids.items():
            console.print(f"    {name_val}: [dim]{uuid_val}[/dim]")
    if edge_errors:
        for err in edge_errors:
            console.print(f"  [yellow]Warning:[/yellow] {err}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.argument("kengram_id", required=False)
@_json_flag
def show(kengram_id: str | None, output_json: bool):
    """Show a kEngram's details."""
    store = _get_storage()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            msg = f"kEngram '{kengram_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return
    if output_json:
        click.echo(json.dumps(manifest.to_dict()))
        return
    console.print(Panel(
        f"[bold]{manifest.name}[/bold]\n\n"
        f"  ID: [dim]{manifest.id}[/dim]\n"
        f"  Type: {manifest.kengram_type}\n"
        f"  Group: [dim]{manifest.group_id}[/dim]\n"
        f"  Nodes: {len(manifest.pinned_nodes)}\n"
        f"  Edges: {len(manifest.pinned_edges)}\n"
        f"  Episodes: {len(manifest.episodes)}\n"
        f"  Merkle: [dim]{manifest.merkle_root[:16]}...[/dim]\n"
        f"  Summary: {manifest.summary or '[dim]empty[/dim]'}\n"
        f"  Updated: {manifest.updated_at}",
        title="kEngram", border_style="bright_blue",
    ))
    if manifest.pinned_nodes:
        console.print("\n[bold]Pinned Nodes:[/bold]")
        for node_uuid in manifest.pinned_nodes:
            console.print(f"  [dim]{node_uuid}[/dim]")
    if manifest.pinned_edges:
        console.print("\n[bold]Pinned Edges:[/bold]")
        for key in manifest.pinned_edges:
            console.print(f"  [dim]{key}[/dim]")


@kengram.command(name="list")
@_json_flag
def list_cmd(output_json: bool):
    """List all kEngrams."""
    store = _get_storage()
    items = store.list_all()
    active_id = store.get_active()
    if output_json:
        click.echo(json.dumps({"kengrams": items}))
        return
    if not items:
        console.print("[dim]No kEngrams found.[/dim]")
        return
    table = Table(title="kEngrams", title_style="bold")
    table.add_column("", width=2)
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Nodes", justify="right")
    table.add_column("Merkle", style="dim")
    table.add_column("Updated")
    for item in items:
        marker = "[green]*[/green]" if item["id"] == active_id else ""
        table.add_row(
            marker, item["id"], item["name"], item["type"],
            str(item["nodes"]), item["merkle_root"], item.get("updated_at", "")[:10],
        )
    console.print(table)


@kengram.command()
@click.argument("text")
@click.option("--to", "target_id", default=None, help="Target kEngram ID (default: active).")
@_json_flag
def summary(text: str, target_id: str | None, output_json: bool):
    """Update a kEngram's summary text."""
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            msg = f"kEngram '{target_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return
    manifest.update_summary(text)
    store.save(manifest)
    if output_json:
        click.echo(json.dumps({"status": "updated", "id": manifest.id}))
        return
    console.print(f"[green]Updated[/green] summary for {manifest.id}")


@kengram.command()
@click.argument("kengram_id")
@_json_flag
def use(kengram_id: str, output_json: bool):
    """Set the active kEngram."""
    store = _get_storage()
    manifest = store.load(kengram_id)
    if not manifest:
        msg = f"kEngram '{kengram_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    store.set_active(kengram_id)
    if output_json:
        click.echo(json.dumps({"status": "active", "id": kengram_id, "name": manifest.name}))
        return
    console.print(f"[green]Active:[/green] {manifest.name} ({kengram_id})")


@kengram.command()
@click.argument("source_id")
@click.option("--into", "target_id", required=True, help="Target kEngram ID.")
@_json_flag
def merge(source_id: str, target_id: str, output_json: bool):
    """Merge a session kEngram into a topic kEngram."""
    store = _get_storage()
    source = store.load(source_id)
    if not source:
        msg = f"Source '{source_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    target = store.load(target_id)
    if not target:
        msg = f"Target '{target_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    old_root = target.merkle_root
    target.merge(source)
    store.save(target)
    changed = target.merkle_root != old_root
    if output_json:
        click.echo(json.dumps({
            "status": "merged" if changed else "no_change",
            "source": source_id,
            "target": target_id,
            "nodes": len(target.pinned_nodes),
            "edges": len(target.pinned_edges),
            "merkle_root": target.merkle_root,
        }))
        return
    if changed:
        console.print(f"[green]Merged[/green] {source_id} → {target_id}")
        console.print(f"  Nodes: {len(target.pinned_nodes)}, Edges: {len(target.pinned_edges)}")
        console.print(f"  New merkle root: [dim]{target.merkle_root[:16]}...[/dim]")
    else:
        console.print(f"[dim]No-op:[/dim] {source_id} already merged into {target_id}")


@kengram.command()
@click.argument("kengram_id")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
@_json_flag
def delete(kengram_id: str, force: bool, output_json: bool):
    """Delete a kEngram by ID."""
    store = _get_storage()
    manifest = store.load(kengram_id)
    if not manifest:
        msg = f"kEngram '{kengram_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    if not force and not output_json:
        click.confirm(f"Delete kEngram '{manifest.name}' ({kengram_id})?", abort=True)
    store.delete(kengram_id)
    if output_json:
        click.echo(json.dumps({"status": "deleted", "id": kengram_id}))
        return
    console.print(f"[red]Deleted[/red] {kengram_id}")


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option("--format", "fmt", default="canvas", type=click.Choice(["canvas", "plan"]))
@_json_flag
def export(kengram_id: str | None, fmt: str, output_json: bool):
    """Export a kEngram to Obsidian canvas or markdown plan format."""
    store = _get_storage()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            msg = f"kEngram '{kengram_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return
    entities = []
    for node_uuid in manifest.pinned_nodes:
        meta = manifest._node_meta.get(node_uuid, {})
        entities.append({
            "uuid": node_uuid,
            "name": meta.get("name", node_uuid[:12]),
            "summary": meta.get("summary", ""),
            "labels": meta.get("labels", []),
        })
    edges = []
    for key in manifest.pinned_edges:
        parts = key.split(":", 2)
        if len(parts) == 3:
            edges.append({
                "source_node_uuid": parts[0],
                "target_node_uuid": parts[1],
                "name": parts[2],
                "fact": "",
            })
    if fmt == "plan":
        from bonfires.kengram.plan_export import export_plan

        md = export_plan(manifest, entities, edges)
        plan_path = store.save_plan(manifest.id, manifest.name, md)
        if output_json:
            click.echo(json.dumps({"status": "exported", "id": manifest.id, "path": str(plan_path)}))
            return
        console.print(f"[green]Exported[/green] {manifest.id} → {plan_path}")
        return

    # Canvas format (default)
    # Run verify to get per-node KG sync status for coloring
    node_status = _verify_for_export(manifest)
    canvas_data = export_canvas(manifest, entities=entities, edges=edges, node_status=node_status)
    path = store.save_canvas(manifest.id, canvas_data)
    if output_json:
        click.echo(json.dumps({"status": "exported", "id": manifest.id, "path": str(path)}))
        return
    console.print(f"[green]Exported[/green] {manifest.id} → {path}")


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option("--local", "local_only", is_flag=True, help="Skip API verification, check locally only.")
@_json_flag
def verify(kengram_id: str | None, local_only: bool, output_json: bool):
    """Verify a kEngram's merkle root against stored hashes."""
    store = _get_storage()
    cfg = get_config()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            msg = f"kEngram '{kengram_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return

    from bonfires.kengram.hashing import hash_node
    from bonfires.kengram.hashing import merkle_root as compute_merkle

    if not local_only and manifest.pinned_nodes:
        fetched = kg_client.fetch_entities_batch(cfg, manifest.pinned_nodes)
        if fetched is None:
            if not output_json:
                console.print(
                    "[yellow]Warning:[/yellow] Could not reach KG API, falling back to local verification."
                )
        else:
            entity_map: dict[str, dict[str, Any]] = {
                str(e["uuid"]): e for e in fetched
            }
            kg_node_hashes: dict[str, str] = {}
            node_results: dict[str, dict[str, str]] = {}
            for node_uuid in manifest.pinned_nodes:
                entity = entity_map.get(node_uuid)
                if entity is None:
                    if not output_json:
                        console.print(f"  {node_uuid[:12]}  [yellow]NOT IN KG[/yellow]")
                    kg_node_hashes[node_uuid] = manifest._node_hashes.get(node_uuid, "")
                    node_results[node_uuid] = {"status": "not_in_kg"}
                    continue
                kg_hash = hash_node(
                    node_uuid,
                    str(entity.get("name", "")),
                    str(entity.get("summary", "")),
                    list(entity.get("labels", [])),
                )
                kg_node_hashes[node_uuid] = kg_hash
                stored_hash = manifest._node_hashes.get(node_uuid, "")
                if kg_hash == stored_hash:
                    if not output_json:
                        console.print(f"  {node_uuid[:12]}  [green]OK[/green]")
                    node_results[node_uuid] = {"status": "ok"}
                else:
                    if not output_json:
                        console.print(
                            f"  {node_uuid[:12]}  [yellow]DRIFT[/yellow]"
                            f"  stored={stored_hash[:12]}.. kg={kg_hash[:12]}.."
                        )
                    node_results[node_uuid] = {
                        "status": "drift",
                        "stored_hash": stored_hash,
                        "kg_hash": kg_hash,
                    }

            if not output_json:
                console.print("[dim]Edge verification: local-only (no batch edge endpoint)[/dim]")

            # Canvas diff: check for unpushed local edits
            canvas_dirty = _check_canvas_diff(manifest, cfg["vault_dir"])
            if canvas_dirty:
                for dirty_uuid, info in canvas_dirty.items():
                    node_results[dirty_uuid] = info
                    if not output_json:
                        changes_str = ", ".join(info.get("changes", []))
                        console.print(
                            f"  {dirty_uuid[:12]}  [bold orange1]MODIFIED[/bold orange1]  {changes_str}"
                        )

            all_hashes = list(kg_node_hashes.values()) + list(manifest._edge_hashes.values())
            recomputed = compute_merkle(all_hashes)
            verified = recomputed == manifest.merkle_root
            has_canvas_changes = len(canvas_dirty) > 0
            if output_json:
                click.echo(json.dumps({
                    "status": "verified" if verified and not has_canvas_changes else "drift",
                    "id": manifest.id,
                    "merkle_root": manifest.merkle_root,
                    "recomputed_root": recomputed,
                    "nodes": node_results,
                    "canvas_modified": len(canvas_dirty),
                }))
                return
            if has_canvas_changes:
                console.print(
                    f"[bold orange1]{len(canvas_dirty)} node(s) modified on canvas — push to sync[/bold orange1]"
                )
            if verified and not has_canvas_changes:
                console.print(f"[green]Verified[/green] {manifest.id}")
                console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
                console.print(f"  Nodes: {len(manifest.pinned_nodes)}, Edges: {len(manifest.pinned_edges)}")
            elif has_canvas_changes and verified:
                console.print("[yellow]KG in sync[/yellow] but canvas has unpushed changes")
                console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
            else:
                console.print(f"[red]DRIFT DETECTED[/red] in {manifest.id}")
                console.print(f"  Stored root:     [dim]{manifest.merkle_root[:16]}...[/dim]")
                console.print(f"  Recomputed root: [dim]{recomputed[:16]}...[/dim]")
            _verify_plan_structure(manifest, output_json)
            return

    # Local-only verification (--local flag or API fallback or no pinned nodes)
    all_hashes = list(manifest._node_hashes.values()) + list(manifest._edge_hashes.values())
    recomputed = compute_merkle(all_hashes)
    verified = recomputed == manifest.merkle_root
    if output_json:
        node_results_local: dict[str, dict[str, str]] = {}
        for node_uuid in manifest.pinned_nodes:
            node_results_local[node_uuid] = {"status": "local_only"}
        click.echo(json.dumps({
            "status": "verified" if verified else "drift",
            "id": manifest.id,
            "merkle_root": manifest.merkle_root,
            "recomputed_root": recomputed,
            "nodes": node_results_local,
        }))
        return
    if verified:
        console.print(f"[green]Verified[/green] {manifest.id}")
        console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
        console.print(f"  Nodes: {len(manifest.pinned_nodes)}, Edges: {len(manifest.pinned_edges)}")
    else:
        console.print(f"[red]DRIFT DETECTED[/red] in {manifest.id}")
        console.print(f"  Stored root:     [dim]{manifest.merkle_root[:16]}...[/dim]")
        console.print(f"  Recomputed root: [dim]{recomputed[:16]}...[/dim]")

    # Plan structural verification: check if this is a plan kEngram (has Goal entity)
    _verify_plan_structure(manifest, output_json)


def _verify_plan_structure(manifest: KEngramManifest, output_json: bool) -> None:
    """Check plan-specific structure: orphan tasks and DEPENDS_ON cycles."""
    goal_nodes = [
        u for u in manifest.pinned_nodes
        if "Goal" in (manifest._node_meta.get(u, {}).get("labels", []))
    ]
    if not goal_nodes:
        return

    task_nodes = [
        u for u in manifest.pinned_nodes
        if "Task" in (manifest._node_meta.get(u, {}).get("labels", []))
        and "Goal" not in (manifest._node_meta.get(u, {}).get("labels", []))
    ]
    if not task_nodes:
        return

    if not output_json:
        console.print("\n[bold]Plan structure:[/bold]")

    # Check all tasks reachable from Goal via DECOMPOSES_INTO
    decomp_targets: set[str] = set()
    for key in manifest.pinned_edges:
        parts = key.split(":", 2)
        if len(parts) == 3 and parts[2] == "DECOMPOSES_INTO":
            decomp_targets.add(parts[1])
    orphans = [u for u in task_nodes if u not in decomp_targets]
    if orphans and not output_json:
        console.print(
            f"  [yellow]Warning:[/yellow] {len(orphans)} task(s) not linked"
            " from Goal via DECOMPOSES_INTO"
        )

    # Check DEPENDS_ON is a DAG (no cycles) via topological sort
    from bonfires.kengram.plan_export import topological_sort

    depends_edges: list[dict[str, str]] = []
    for key in manifest.pinned_edges:
        parts = key.split(":", 2)
        if len(parts) == 3 and parts[2] == "DEPENDS_ON":
            depends_edges.append({
                "source_node_uuid": parts[0],
                "target_node_uuid": parts[1],
                "name": "DEPENDS_ON",
            })
    sorted_uuids = topological_sort(task_nodes, depends_edges)
    # If any task wasn't placed by the sort, it's in a cycle
    cycle_members = [u for u in task_nodes if u not in sorted_uuids[:len(task_nodes)]]
    if not output_json:
        if cycle_members:
            console.print(
                f"  [red]Error:[/red] DEPENDS_ON cycle detected"
                f" involving {len(cycle_members)} task(s)"
            )
        elif not orphans:
            console.print("  [green]OK[/green] All tasks linked, no dependency cycles")


@kengram.command()
@click.argument("name")
@click.option("--labels", default="Entity", help="Comma-separated labels.")
@click.option("--summary", default="", help="Entity summary.")
@_json_flag
def create(name: str, labels: str, summary: str, output_json: bool) -> None:
    """Create a new entity in the KG and pin it to the active kEngram."""
    cfg = get_config()
    store = _get_storage()
    manifest = _get_active_manifest(store, json_mode=output_json)
    if not manifest:
        return
    label_list = [lb.strip() for lb in labels.split(",") if lb.strip()]
    attributes: dict[str, Any] = {"summary": summary} if summary else {}
    uuid = kg_client.create_entity(cfg, name, label_list, attributes)
    if not uuid:
        msg = "Failed to create entity in KG."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return
    # Fetch back from KG to get canonical labels (server may add Entity, etc.)
    entity = kg_client.fetch_entity(cfg, uuid)
    if entity:
        pin_name = str(entity.get("name", name))
        pin_summary = str(entity.get("summary", summary))
        pin_labels = list(entity.get("labels", label_list))
    else:
        pin_name, pin_summary, pin_labels = name, summary, label_list
    manifest.pin_node(uuid=uuid, name=pin_name, summary=pin_summary, labels=pin_labels)
    store.save(manifest)
    if output_json:
        click.echo(json.dumps({
            "status": "created_and_pinned",
            "uuid": uuid,
            "name": name,
            "merkle_root": manifest.merkle_root,
        }))
        return
    console.print(f"[green]Created + Pinned[/green] {uuid}")
    console.print(f"  Name: {name}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.option("--id", "target_id", default=None, help="kEngram ID (default: active).")
@click.option("--changes", "changes_json", default=None, help="JSON describing canvas modifications.")
@_json_flag
def push(target_id: str | None, changes_json: str | None, output_json: bool) -> None:
    """Push local-only nodes and edges to the canonical KG."""
    from bonfires.kengram.hashing import hash_node

    cfg = get_config()
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            msg = f"kEngram '{target_id}' not found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
    else:
        manifest = _get_active_manifest(store, json_mode=output_json)
        if not manifest:
            return

    nodes_pushed = 0
    nodes_skipped = 0
    pushed_uuid_pairs: list[tuple[str, str]] = []

    for node_uuid in manifest.pinned_nodes:
        existing = kg_client.fetch_entity(cfg, node_uuid)
        if existing is not None:
            nodes_skipped += 1
            continue
        meta = manifest._node_meta.get(node_uuid, {})
        node_name = str(meta.get("name", ""))
        node_summary = str(meta.get("summary", ""))
        node_labels = list(meta.get("labels", []))
        attributes: dict[str, Any] = {"summary": node_summary} if node_summary else {}
        result_uuid = kg_client.create_entity(cfg, node_name, node_labels, attributes)
        if result_uuid is not None:
            nodes_pushed += 1
            pushed_uuid_pairs.append((node_uuid, result_uuid))
        else:
            nodes_skipped += 1

    # Re-pin pushed nodes: fetch canonical data back and update hashes
    for local_uuid, canonical_uuid in pushed_uuid_pairs:
        entity = kg_client.fetch_entity(cfg, canonical_uuid)
        if entity:
            new_name = str(entity.get("name", ""))
            new_summary = str(entity.get("summary", ""))
            new_labels = list(entity.get("labels", []))
            new_hash = hash_node(canonical_uuid, new_name, new_summary, new_labels)
            if canonical_uuid != local_uuid:
                # Server assigned a different canonical UUID — migrate manifest entries
                manifest._node_hashes.pop(local_uuid, None)
                manifest._node_meta.pop(local_uuid, None)
                if local_uuid in manifest.pinned_nodes:
                    manifest.pinned_nodes.remove(local_uuid)
                    manifest.pinned_nodes.append(canonical_uuid)
            manifest._node_hashes[canonical_uuid] = new_hash
            manifest._node_meta[canonical_uuid] = {
                "name": new_name,
                "summary": new_summary,
                "labels": new_labels,
            }

    if pushed_uuid_pairs:
        manifest._recompute_merkle()

    edges_pushed = 0
    edges_skipped = 0

    for edge_key in manifest.pinned_edges:
        parts = edge_key.split(":", 2)
        if len(parts) != 3:
            edges_skipped += 1
            continue
        source_uuid, target_uuid, edge_name = parts[0], parts[1], parts[2]
        result = kg_client.create_edge(cfg, source_uuid, target_uuid, edge_name, "")
        if result is not None:
            edges_pushed += 1
        else:
            edges_skipped += 1

    # --- Canvas changes processing ---
    nodes_updated = 0
    nodes_created = 0
    edges_created = 0

    if changes_json:
        try:
            changes = json.loads(changes_json)
        except json.JSONDecodeError:
            changes = {}

        dirty = changes.get("dirty", {})
        new_nodes = changes.get("new_nodes", {})
        new_edges = changes.get("new_edges", [])

        # 1. Update dirty (modified) nodes
        for node_uuid, node_data in dirty.items():
            node_name = str(node_data.get("name", ""))
            node_summary = str(node_data.get("summary", ""))
            node_labels = list(node_data.get("labels", []))
            result = kg_client.update_entity(cfg, node_uuid, node_name, node_labels, node_summary)
            if result is not None:
                nodes_updated += 1
                # Audit edge: record modification in KG
                kg_client.create_edge(
                    cfg,
                    node_uuid,
                    node_uuid,
                    "MODIFIED_VIA_KENGRAM",
                    f"Entity updated via kEngram canvas: name='{node_name}', labels={node_labels}",
                )
                # Re-pin: fetch canonical data back from KG to ensure hash matches verify
                canonical = kg_client.fetch_entity(cfg, node_uuid)
                if canonical:
                    canon_name = str(canonical.get("name", node_name))
                    canon_summary = str(canonical.get("summary", node_summary))
                    canon_labels = list(canonical.get("labels", node_labels))
                else:
                    canon_name, canon_summary, canon_labels = node_name, node_summary, node_labels
                new_hash = hash_node(node_uuid, canon_name, canon_summary, canon_labels)
                manifest._node_hashes[node_uuid] = new_hash
                manifest._node_meta[node_uuid] = {
                    "name": canon_name,
                    "summary": canon_summary,
                    "labels": canon_labels,
                }

        # 2. Create new canvas nodes
        canvas_id_to_uuid: dict[str, str] = {}
        for canvas_id, node_data in new_nodes.items():
            node_name = str(node_data.get("name", ""))
            node_summary = str(node_data.get("summary", ""))
            node_labels = list(node_data.get("labels", []))
            attributes: dict[str, Any] = {"summary": node_summary} if node_summary else {}
            result_uuid = kg_client.create_entity(cfg, node_name, node_labels, attributes)
            if result_uuid is not None:
                nodes_created += 1
                canvas_id_to_uuid[canvas_id] = result_uuid
                # Pin to manifest
                manifest.pinned_nodes.append(result_uuid)
                new_hash = hash_node(result_uuid, node_name, node_summary, node_labels)
                manifest._node_hashes[result_uuid] = new_hash
                manifest._node_meta[result_uuid] = {
                    "name": node_name,
                    "summary": node_summary,
                    "labels": node_labels,
                }

        # 3. Create new canvas edges
        for edge_data in new_edges:
            from_id = str(edge_data.get("from", ""))
            to_id = str(edge_data.get("to", ""))
            edge_label = str(edge_data.get("label", ""))
            # Resolve canvas IDs to UUIDs for newly created nodes
            from_uuid = canvas_id_to_uuid.get(from_id, from_id)
            to_uuid = canvas_id_to_uuid.get(to_id, to_id)
            if from_uuid and to_uuid and edge_label:
                result = kg_client.create_edge(cfg, from_uuid, to_uuid, edge_label, "")
                if result is not None:
                    edges_created += 1
                    # Pin edge to manifest
                    edge_key = f"{from_uuid}:{to_uuid}:{edge_label}"
                    manifest.pinned_edges.append(edge_key)
                    manifest._edge_hashes[edge_key] = edge_key  # placeholder hash

        if nodes_updated or nodes_created or edges_created:
            manifest._recompute_merkle()

    store.save(manifest)

    if output_json:
        click.echo(json.dumps({
            "status": "pushed",
            "kengram_id": manifest.id,
            "nodes_pushed": nodes_pushed,
            "nodes_skipped": nodes_skipped,
            "edges_pushed": edges_pushed,
            "edges_skipped": edges_skipped,
            "nodes_updated": nodes_updated,
            "nodes_created": nodes_created,
            "edges_created": edges_created,
            "merkle_root": manifest.merkle_root,
        }))
        return

    console.print(f"[green]Pushed[/green] {manifest.id}")
    console.print(f"  Nodes pushed:  {nodes_pushed}")
    console.print(f"  Nodes skipped: {nodes_skipped}")
    console.print(f"  Edges pushed:  {edges_pushed}")
    console.print(f"  Edges skipped: {edges_skipped}")
    if nodes_updated:
        console.print(f"  Nodes updated: {nodes_updated}")
    if nodes_created:
        console.print(f"  Nodes created: {nodes_created}")
    if edges_created:
        console.print(f"  Edges created: {edges_created}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.argument("uuid")
@_json_flag
def repin(uuid: str, output_json: bool):
    """Re-fetch entity from KG and update hash in active kEngram."""
    cfg = get_config()
    store = _get_storage()
    manifest = _get_active_manifest(store, json_mode=output_json)
    if not manifest:
        return

    if uuid not in manifest.pinned_nodes:
        msg = f"UUID '{uuid}' is not pinned in the active kEngram."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    entity = kg_client.fetch_entity(cfg, uuid)
    if not entity:
        msg = f"Could not fetch entity '{uuid}' from KG."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    from bonfires.kengram.hashing import hash_node

    new_name = str(entity.get("name", ""))
    new_summary = str(entity.get("summary", ""))
    new_labels = list(entity.get("labels", []))

    old_hash = manifest._node_hashes.get(uuid, "")
    new_hash = hash_node(uuid, new_name, new_summary, new_labels)

    manifest._node_hashes[uuid] = new_hash
    manifest._node_meta[uuid] = {"name": new_name, "summary": new_summary, "labels": new_labels}
    manifest._recompute_merkle()
    store.save(manifest)

    changed = old_hash != new_hash
    if output_json:
        click.echo(json.dumps({
            "status": "repinned",
            "uuid": uuid,
            "kengram_id": manifest.id,
            "changed": changed,
            "merkle_root": manifest.merkle_root,
        }))
        return
    if changed:
        console.print(f"[green]Repinned[/green] {uuid} — hash updated")
    else:
        console.print(f"[green]Repinned[/green] {uuid} — no change")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
