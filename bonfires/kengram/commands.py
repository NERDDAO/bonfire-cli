"""CLI commands for kEngram management."""

from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires.config import get_config
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
@click.argument("uuid")
@click.option("--to", "target_id", default=None, help="Target kEngram ID (default: active).")
@click.option("--name", "node_name", default="", help="Entity name.")
@click.option("--summary", default="", help="Entity summary.")
@click.option("--labels", default="", help="Comma-separated labels.")
def pin(uuid: str, target_id: str | None, node_name: str, summary: str, labels: str):
    """Pin a KG entity to a kEngram."""
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
    label_list = [lb.strip() for lb in labels.split(",") if lb.strip()] if labels else []
    manifest.pin_node(uuid=uuid, name=node_name, summary=summary, labels=label_list)
    store.save(manifest)
    console.print(f"[green]Pinned[/green] {uuid} to {manifest.id}")
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
    entities = [
        {"uuid": node_uuid, "name": node_uuid[:12], "summary": "", "labels": []}
        for node_uuid in manifest.pinned_nodes
    ]
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
def verify(kengram_id: str | None):
    """Verify a kEngram's merkle root against stored hashes."""
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
    from bonfires.kengram.hashing import merkle_root as compute_merkle
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
