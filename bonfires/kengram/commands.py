"""CLI commands for kEngram management."""

from __future__ import annotations

from typing import Any

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


def _get_storage() -> KEngramStorage:
    cfg = get_config()
    return KEngramStorage(cfg["vault_dir"])


def _get_active_manifest(store: KEngramStorage) -> KEngramManifest | None:
    active_id = store.get_active()
    if not active_id:
        console.print("[red]No active kEngram. Run `bonfire kengram new` first.[/red]")
        return None
    manifest = store.load(active_id)
    if not manifest:
        console.print(f"[red]Active kEngram '{active_id}' not found.[/red]")
        return None
    return manifest


@click.group()
def kengram():
    """Manage kEngrams — verifiable knowledge subgraphs."""


@kengram.command()
@click.argument("name")
@click.option("--type", "kengram_type", default="session", type=click.Choice(["session", "topic"]))
@click.option("--parent", default=None, help="Parent topic kEngram ID.")
def new(name: str, kengram_type: str, parent: str | None):
    """Create a new kEngram."""
    cfg = get_config()
    store = _get_storage()
    manifest = KEngramManifest.create(
        name=name, kengram_type=kengram_type, group_id=cfg["group_id"], parent_topic=parent,
    )
    path = store.save(manifest)
    store.set_active(manifest.id)
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
def pin(
    uuid: str | None,
    target_id: str | None,
    node_name: str,
    summary: str,
    labels: str,
    search_query: str | None,
):
    """Pin a KG entity to a kEngram."""
    cfg = get_config()
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            console.print(f"[red]kEngram '{target_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
        if not manifest:
            return

    if search_query:
        results = kg_client.search_entities(cfg, search_query)
        if not results:
            console.print("[red]No results found.[/red]")
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
                console.print(
                    "[yellow]Warning:[/yellow] Could not fetch entity from KG, using provided metadata."
                )
                pin_name = node_name
                pin_summary = summary
                pin_labels = [lb.strip() for lb in labels.split(",") if lb.strip()] if labels else []
    else:
        console.print("[red]Provide a UUID or use --search.[/red]")
        return

    manifest.pin_node(uuid=pin_uuid, name=pin_name, summary=pin_summary, labels=pin_labels)
    store.save(manifest)
    console.print(f"[green]Pinned[/green] {pin_uuid} to {manifest.id}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.argument("uuid")
@click.option("--from", "source_id", default=None, help="Source kEngram ID (default: active).")
def unpin(uuid: str, source_id: str | None):
    """Remove a node from a kEngram."""
    store = _get_storage()
    if source_id:
        manifest = store.load(source_id)
        if not manifest:
            console.print(f"[red]kEngram '{source_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
        if not manifest:
            return
    manifest.unpin_node(uuid)
    store.save(manifest)
    console.print(f"[yellow]Unpinned[/yellow] {uuid} from {manifest.id}")


@kengram.command()
@click.argument("source")
@click.argument("target")
@click.option("--name", "edge_name", required=True, help="Relationship name (e.g. USES, PRODUCES).")
@click.option("--fact", default="", help="Relationship description.")
def edge(source: str, target: str, edge_name: str, fact: str):
    """Add an edge between two pinned nodes."""
    store = _get_storage()
    manifest = _get_active_manifest(store)
    if not manifest:
        return
    if source not in manifest.pinned_nodes:
        console.print(f"[red]Source '{source}' is not pinned.[/red]")
        return
    if target not in manifest.pinned_nodes:
        console.print(f"[red]Target '{target}' is not pinned.[/red]")
        return

    # Push edge to canonical KG by UUID
    cfg = get_config()
    result = kg_client.create_edge(cfg, source, target, edge_name, fact)
    if result:
        console.print(f"[green]Pushed[/green] edge to canonical KG")
    else:
        console.print("[yellow]Warning:[/yellow] Could not push edge to KG, pinning locally only.")

    manifest.pin_edge(source_uuid=source, target_uuid=target, name=edge_name, fact=fact)
    store.save(manifest)
    console.print(f"[green]Edge[/green] {source[:12]} —[{edge_name}]→ {target[:12]}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


@kengram.command()
@click.argument("kengram_id", required=False)
def show(kengram_id: str | None):
    """Show a kEngram's details."""
    store = _get_storage()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            console.print(f"[red]kEngram '{kengram_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
        if not manifest:
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
def list_cmd():
    """List all kEngrams."""
    store = _get_storage()
    items = store.list_all()
    active_id = store.get_active()
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
def summary(text: str, target_id: str | None):
    """Update a kEngram's summary text."""
    store = _get_storage()
    if target_id:
        manifest = store.load(target_id)
        if not manifest:
            console.print(f"[red]kEngram '{target_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
        if not manifest:
            return
    manifest.update_summary(text)
    store.save(manifest)
    console.print(f"[green]Updated[/green] summary for {manifest.id}")


@kengram.command()
@click.argument("kengram_id")
def use(kengram_id: str):
    """Set the active kEngram."""
    store = _get_storage()
    manifest = store.load(kengram_id)
    if not manifest:
        console.print(f"[red]kEngram '{kengram_id}' not found.[/red]")
        return
    store.set_active(kengram_id)
    console.print(f"[green]Active:[/green] {manifest.name} ({kengram_id})")


@kengram.command()
@click.argument("source_id")
@click.option("--into", "target_id", required=True, help="Target kEngram ID.")
def merge(source_id: str, target_id: str):
    """Merge a session kEngram into a topic kEngram."""
    store = _get_storage()
    source = store.load(source_id)
    if not source:
        console.print(f"[red]Source '{source_id}' not found.[/red]")
        return
    target = store.load(target_id)
    if not target:
        console.print(f"[red]Target '{target_id}' not found.[/red]")
        return
    old_root = target.merkle_root
    target.merge(source)
    store.save(target)
    changed = target.merkle_root != old_root
    if changed:
        console.print(f"[green]Merged[/green] {source_id} → {target_id}")
        console.print(f"  Nodes: {len(target.pinned_nodes)}, Edges: {len(target.pinned_edges)}")
        console.print(f"  New merkle root: [dim]{target.merkle_root[:16]}...[/dim]")
    else:
        console.print(f"[dim]No-op:[/dim] {source_id} already merged into {target_id}")


@kengram.command()
@click.argument("kengram_id")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
def delete(kengram_id: str, force: bool):
    """Delete a kEngram by ID."""
    store = _get_storage()
    manifest = store.load(kengram_id)
    if not manifest:
        console.print(f"[red]kEngram '{kengram_id}' not found.[/red]")
        return
    if not force:
        click.confirm(f"Delete kEngram '{manifest.name}' ({kengram_id})?", abort=True)
    store.delete(kengram_id)
    console.print(f"[red]Deleted[/red] {kengram_id}")


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option("--format", "fmt", default="canvas", type=click.Choice(["canvas"]))
def export(kengram_id: str | None, fmt: str):
    """Export a kEngram to Obsidian canvas format."""
    store = _get_storage()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            console.print(f"[red]kEngram '{kengram_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
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
    canvas_data = export_canvas(manifest, entities=entities, edges=edges)
    path = store.save_canvas(manifest.id, canvas_data)
    console.print(f"[green]Exported[/green] {manifest.id} → {path}")


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option("--local", "local_only", is_flag=True, help="Skip API verification, check locally only.")
def verify(kengram_id: str | None, local_only: bool):
    """Verify a kEngram's merkle root against stored hashes."""
    store = _get_storage()
    cfg = get_config()
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            console.print(f"[red]kEngram '{kengram_id}' not found.[/red]")
            return
    else:
        manifest = _get_active_manifest(store)
        if not manifest:
            return

    from bonfires.kengram.hashing import hash_node
    from bonfires.kengram.hashing import merkle_root as compute_merkle

    if not local_only and manifest.pinned_nodes:
        fetched = kg_client.fetch_entities_batch(cfg, manifest.pinned_nodes)
        if fetched is None:
            console.print(
                "[yellow]Warning:[/yellow] Could not reach KG API, falling back to local verification."
            )
        else:
            entity_map: dict[str, dict[str, Any]] = {
                str(e["uuid"]): e for e in fetched
            }
            kg_node_hashes: dict[str, str] = {}
            for node_uuid in manifest.pinned_nodes:
                entity = entity_map.get(node_uuid)
                if entity is None:
                    console.print(f"  {node_uuid[:12]}  [yellow]NOT IN KG[/yellow]")
                    kg_node_hashes[node_uuid] = manifest._node_hashes.get(node_uuid, "")
                    continue
                kg_hash = hash_node(
                    node_uuid,
                    str(entity.get("name", "")),
                    str(entity.get("summary", "")),
                    list(entity.get("labels", [])),  # type narrowing for list
                )
                kg_node_hashes[node_uuid] = kg_hash
                stored_hash = manifest._node_hashes.get(node_uuid, "")
                if kg_hash == stored_hash:
                    console.print(f"  {node_uuid[:12]}  [green]OK[/green]")
                else:
                    console.print(
                        f"  {node_uuid[:12]}  [yellow]DRIFT[/yellow]"
                        f"  stored={stored_hash[:12]}.. kg={kg_hash[:12]}.."
                    )

            console.print("[dim]Edge verification: local-only (no batch edge endpoint)[/dim]")

            all_hashes = list(kg_node_hashes.values()) + list(manifest._edge_hashes.values())
            recomputed = compute_merkle(all_hashes)
            if recomputed == manifest.merkle_root:
                console.print(f"[green]Verified[/green] {manifest.id}")
                console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
                console.print(f"  Nodes: {len(manifest.pinned_nodes)}, Edges: {len(manifest.pinned_edges)}")
            else:
                console.print(f"[red]DRIFT DETECTED[/red] in {manifest.id}")
                console.print(f"  Stored root:     [dim]{manifest.merkle_root[:16]}...[/dim]")
                console.print(f"  Recomputed root: [dim]{recomputed[:16]}...[/dim]")
            return

    # Local-only verification (--local flag or API fallback or no pinned nodes)
    all_hashes = list(manifest._node_hashes.values()) + list(manifest._edge_hashes.values())
    recomputed = compute_merkle(all_hashes)
    if recomputed == manifest.merkle_root:
        console.print(f"[green]Verified[/green] {manifest.id}")
        console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
        console.print(f"  Nodes: {len(manifest.pinned_nodes)}, Edges: {len(manifest.pinned_edges)}")
    else:
        console.print(f"[red]DRIFT DETECTED[/red] in {manifest.id}")
        console.print(f"  Stored root:     [dim]{manifest.merkle_root[:16]}...[/dim]")
        console.print(f"  Recomputed root: [dim]{recomputed[:16]}...[/dim]")


@kengram.command()
@click.argument("name")
@click.option("--labels", default="Entity", help="Comma-separated labels.")
@click.option("--summary", default="", help="Entity summary.")
def create(name: str, labels: str, summary: str) -> None:
    """Create a new entity in the KG and pin it to the active kEngram."""
    cfg = get_config()
    store = _get_storage()
    manifest = _get_active_manifest(store)
    if not manifest:
        return
    label_list = [lb.strip() for lb in labels.split(",") if lb.strip()]
    attributes: dict[str, Any] = {"summary": summary} if summary else {}
    uuid = kg_client.create_entity(cfg, name, label_list, attributes)
    if not uuid:
        console.print("[red]Failed to create entity in KG.[/red]")
        return
    manifest.pin_node(uuid=uuid, name=name, summary=summary, labels=label_list)
    store.save(manifest)
    console.print(f"[green]Created + Pinned[/green] {uuid}")
    console.print(f"  Name: {name}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
