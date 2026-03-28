"""CLI commands for kEngram management.

Thin Click shell — all business logic lives in bonfires.sdk.kengram.
"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires.sdk import BonfiresClient
from bonfires.sdk.exceptions import APIError, BonfiresError, ConfigError, NotFoundError

console = Console()

_json_flag = click.option("--json", "output_json", is_flag=True, help="Output as JSON.")


def _json_error(msg: str) -> NoReturn:
    """Print a JSON error object and exit with code 1."""
    click.echo(json.dumps({"error": msg}))
    sys.exit(1)


def _get_client() -> BonfiresClient:
    """Build a BonfiresClient from env config."""
    try:
        return BonfiresClient()
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Run [bold]bonfire init[/bold] to set up your configuration.")
        sys.exit(1)


def _handle_error(e: BonfiresError, *, json_mode: bool = False) -> None:
    """Print error and exit."""
    msg = str(e)
    if json_mode:
        _json_error(msg)
    if isinstance(e, APIError):
        console.print(
            Panel(
                e.response_text[:500],
                title=f"API Error {e.status_code}",
                border_style="red",
            )
        )
    else:
        console.print(f"[red]{msg}[/red]")
    sys.exit(1)


@click.group()
def kengram():
    """Manage kEngrams — verifiable knowledge subgraphs."""


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("name")
@click.option(
    "--type", "kengram_type", default="session", type=click.Choice(["session", "topic"])
)
@click.option("--parent", default=None, help="Parent topic kEngram ID.")
@_json_flag
def new(name: str, kengram_type: str, parent: str | None, output_json: bool):
    """Create a new kEngram."""
    client = _get_client()
    manifest = client.kengrams.create(name, type=kengram_type, parent=parent)
    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "created",
                    "id": manifest.id,
                    "name": manifest.name,
                    "type": manifest.kengram_type,
                    "group_id": manifest.group_id,
                }
            )
        )
        return
    console.print(
        Panel(
            f"[bold green]Created[/bold green] {manifest.id}\n\n"
            f"  Name: {manifest.name}\n"
            f"  Type: {manifest.kengram_type}\n"
            f"  Group: {manifest.group_id}",
            title="kEngram",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# pin
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("uuid", required=False, default=None)
@click.option(
    "--to", "target_id", default=None, help="Target kEngram ID (default: active)."
)
@click.option("--name", "node_name", default="", help="Entity name.")
@click.option("--summary", default="", help="Entity summary.")
@click.option("--labels", default="", help="Comma-separated labels.")
@click.option(
    "--search", "search_query", default=None, help="Search KG for entities to pin."
)
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
    client = _get_client()
    try:
        kengram_id = target_id or client.kengrams.get_active().id
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return  # unreachable but appeases type checker

    if search_query:
        # Interactive search — CLI-only, SDK provides search + pin separately
        try:
            search_result = client.kg.search(search_query)
        except APIError as e:
            _handle_error(e, json_mode=output_json)
            return
        results = search_result.get("entities", [])
        if not results:
            msg = "No results found."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return

        if output_json:
            click.echo(json.dumps({"status": "search_results", "results": results}))
            return

        table = Table(title="Search Results", title_style="bold")
        table.add_column("#", justify="right")
        table.add_column("UUID", style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Labels")
        table.add_column("Summary")
        for i, entity in enumerate(results, 1):
            entity_summary = entity.get("summary", "") or ""
            truncated = (
                entity_summary[:60] + "..."
                if len(entity_summary) > 60
                else entity_summary
            )
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
        pin_name = node_name
        pin_summary = summary
        pin_labels = (
            [lb.strip() for lb in labels.split(",") if lb.strip()] if labels else []
        )
    else:
        msg = "Provide a UUID or use --search."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    try:
        result = client.kengrams.pin(
            kengram_id,
            pin_uuid,
            name=pin_name,
            summary=pin_summary,
            labels=pin_labels if pin_labels else None,
            fetch_from_kg=not bool(pin_name),
        )
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    manifest = result["manifest"]
    enrichment = result.get("enrichment", {})

    if output_json:
        out: dict[str, Any] = {
            "status": "pinned",
            "uuid": pin_uuid,
            "kengram_id": manifest.id,
            "merkle_root": manifest.merkle_root,
        }
        if enrichment:
            out["ontology"] = enrichment
        click.echo(json.dumps(out))
        return
    console.print(f"[green]Pinned[/green] {pin_uuid} to {manifest.id}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
    if enrichment:
        rdf_types = enrichment.get("rdf_types", [])
        auto_filled = enrichment.get("auto_filled", [])
        warnings_list = enrichment.get("warnings", [])
        if rdf_types:
            console.print(f"  OWL types:   [cyan]{', '.join(rdf_types)}[/cyan]")
        if auto_filled:
            console.print(f"  Auto-mapped: [dim]{', '.join(auto_filled)}[/dim]")
        for w in warnings_list:
            console.print(f"  [yellow]Warning:[/yellow] {w}")


# ---------------------------------------------------------------------------
# unpin
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("uuid")
@click.option(
    "--from", "source_id", default=None, help="Source kEngram ID (default: active)."
)
@_json_flag
def unpin(uuid: str, source_id: str | None, output_json: bool):
    """Remove a node from a kEngram."""
    client = _get_client()
    try:
        kengram_id = source_id or client.kengrams.get_active().id
        manifest = client.kengrams.unpin(kengram_id, uuid)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return
    if output_json:
        click.echo(
            json.dumps({"status": "unpinned", "uuid": uuid, "kengram_id": manifest.id})
        )
        return
    console.print(f"[yellow]Unpinned[/yellow] {uuid} from {manifest.id}")


# ---------------------------------------------------------------------------
# edge
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("source")
@click.argument("target")
@click.option(
    "--name",
    "edge_name",
    required=True,
    help="Relationship name (e.g. USES, PRODUCES).",
)
@click.option("--fact", default="", help="Relationship description.")
@click.option(
    "--local", "local_only", is_flag=True, help="Skip KG sync, pin locally only."
)
@_json_flag
def edge(
    source: str,
    target: str,
    edge_name: str,
    fact: str,
    local_only: bool,
    output_json: bool,
):
    """Add an edge between two pinned nodes."""
    client = _get_client()
    try:
        kengram_id = client.kengrams.get_active().id
        result = client.kengrams.add_edge(
            kengram_id, source, target, edge_name, fact, sync_to_kg=not local_only
        )
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    manifest = result["manifest"]
    kg_synced = result["kg_synced"]
    edge_warnings = result.get("warnings", [])

    if not output_json:
        if not local_only:
            if kg_synced:
                console.print("[green]Pushed[/green] edge to canonical KG")
            else:
                console.print(
                    "[yellow]Warning:[/yellow] Could not push edge to KG, pinning locally only."
                )

    if output_json:
        edge_result: dict[str, Any] = {
            "status": "edge_created",
            "source": source,
            "target": target,
            "name": edge_name,
            "merkle_root": manifest.merkle_root,
            "kg_synced": kg_synced,
        }
        if edge_warnings:
            edge_result["warnings"] = edge_warnings
        click.echo(json.dumps(edge_result))
        return
    console.print(f"[green]Edge[/green] {source[:12]} —[{edge_name}]→ {target[:12]}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")
    for w in edge_warnings:
        console.print(f"  [yellow]Warning:[/yellow] {w}")


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("file", required=False, default=None)
@click.option(
    "--to", "target_id", default=None, help="Target kEngram ID (default: active)."
)
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
    client = _get_client()
    try:
        kengram_id = target_id or client.kengrams.get_active().id
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
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

    try:
        result = client.kengrams.batch(
            kengram_id, changeset, sync_to_kg=sync, export_canvas_flag=canvas
        )
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    manifest = result["manifest"]
    edge_errors = result.get("edge_errors", [])
    kg_push_failures = result.get("kg_push_failures", [])

    if edge_errors:
        msg = "Unresolvable edges: " + "; ".join(edge_errors)
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    if kg_push_failures and not output_json:
        for name_val in kg_push_failures:
            console.print(
                f"  [yellow]Warning:[/yellow] Failed to push '{name_val}' to KG, using local UUID"
            )

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "batch_applied",
                    "kengram_id": manifest.id,
                    "nodes_added": result["nodes_added"],
                    "edges_added": result["edges_added"],
                    "generated_uuids": result["generated_uuids"],
                    "merkle_root": manifest.merkle_root,
                }
            )
        )
        return

    console.print(f"[green]Batch applied[/green] to {manifest.id}")
    console.print(f"  Nodes added: {result['nodes_added']}")
    console.print(f"  Edges added: {result['edges_added']}")
    if result["generated_uuids"]:
        console.print("  [bold]Generated UUIDs:[/bold]")
        for name_val, uuid_val in result["generated_uuids"].items():
            console.print(f"    {name_val}: [dim]{uuid_val}[/dim]")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("kengram_id", required=False)
@_json_flag
def show(kengram_id: str | None, output_json: bool):
    """Show a kEngram's details."""
    client = _get_client()
    try:
        manifest = (
            client.kengrams.get(kengram_id)
            if kengram_id
            else client.kengrams.get_active()
        )
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return
    if output_json:
        click.echo(json.dumps(manifest.to_dict()))
        return
    console.print(
        Panel(
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
            title="kEngram",
            border_style="bright_blue",
        )
    )
    if manifest.pinned_nodes:
        console.print("\n[bold]Pinned Nodes:[/bold]")
        for node_uuid in manifest.pinned_nodes:
            console.print(f"  [dim]{node_uuid}[/dim]")
    if manifest.pinned_edges:
        console.print("\n[bold]Pinned Edges:[/bold]")
        for key in manifest.pinned_edges:
            console.print(f"  [dim]{key}[/dim]")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@kengram.command(name="list")
@_json_flag
def list_cmd(output_json: bool):
    """List all kEngrams."""
    client = _get_client()
    items = client.kengrams.list()
    active_id = client.kengrams.get_active_id()
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
            marker,
            item["id"],
            item["name"],
            item["type"],
            str(item["nodes"]),
            item["merkle_root"],
            item.get("updated_at", "")[:10],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("text")
@click.option(
    "--to", "target_id", default=None, help="Target kEngram ID (default: active)."
)
@_json_flag
def summary(text: str, target_id: str | None, output_json: bool):
    """Update a kEngram's summary text."""
    client = _get_client()
    try:
        kengram_id = target_id or client.kengrams.get_active().id
        client.kengrams.update_summary(kengram_id, text)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return
    if output_json:
        click.echo(json.dumps({"status": "updated", "id": kengram_id}))
        return
    console.print(f"[green]Updated[/green] summary for {kengram_id}")


# ---------------------------------------------------------------------------
# use
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("kengram_id")
@_json_flag
def use(kengram_id: str, output_json: bool):
    """Set the active kEngram."""
    client = _get_client()
    try:
        manifest = client.kengrams.get(kengram_id)
        client.kengrams.set_active(kengram_id)
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return
    if output_json:
        click.echo(
            json.dumps({"status": "active", "id": kengram_id, "name": manifest.name})
        )
        return
    console.print(f"[green]Active:[/green] {manifest.name} ({kengram_id})")


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("source_id")
@click.option("--into", "target_id", required=True, help="Target kEngram ID.")
@_json_flag
def merge(source_id: str, target_id: str, output_json: bool):
    """Merge a session kEngram into a topic kEngram."""
    client = _get_client()
    try:
        # Load target before merge to compare merkle root
        old_target = client.kengrams.get(target_id)
        old_root = old_target.merkle_root
        target = client.kengrams.merge(target_id, source_id)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return
    changed = target.merkle_root != old_root
    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "merged" if changed else "no_change",
                    "source": source_id,
                    "target": target_id,
                    "nodes": len(target.pinned_nodes),
                    "edges": len(target.pinned_edges),
                    "merkle_root": target.merkle_root,
                }
            )
        )
        return
    if changed:
        console.print(f"[green]Merged[/green] {source_id} → {target_id}")
        console.print(
            f"  Nodes: {len(target.pinned_nodes)}, Edges: {len(target.pinned_edges)}"
        )
        console.print(f"  New merkle root: [dim]{target.merkle_root[:16]}...[/dim]")
    else:
        console.print(f"[dim]No-op:[/dim] {source_id} already merged into {target_id}")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("kengram_id")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
@_json_flag
def delete(kengram_id: str, force: bool, output_json: bool):
    """Delete a kEngram by ID."""
    client = _get_client()
    try:
        manifest = client.kengrams.get(kengram_id)
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return
    if not force and not output_json:
        click.confirm(f"Delete kEngram '{manifest.name}' ({kengram_id})?", abort=True)
    client.kengrams.delete(kengram_id)
    if output_json:
        click.echo(json.dumps({"status": "deleted", "id": kengram_id}))
        return
    console.print(f"[red]Deleted[/red] {kengram_id}")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option(
    "--format", "fmt", default="canvas", type=click.Choice(["canvas", "plan", "owl"])
)
@click.option(
    "--serialization",
    "serialization",
    default="turtle",
    type=click.Choice(["turtle", "json-ld", "xml"]),
    help="RDF serialization format (only for --format owl).",
)
@_json_flag
def export(kengram_id: str | None, fmt: str, serialization: str, output_json: bool):
    """Export a kEngram to Obsidian canvas, markdown plan, or OWL/RDF format."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        path = client.kengrams.export(kid, format=fmt, serialization=serialization)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return
    if output_json:
        out: dict[str, Any] = {
            "status": "exported",
            "id": kid,
            "format": fmt,
            "path": path,
        }
        if fmt == "owl":
            out["serialization"] = serialization
        click.echo(json.dumps(out))
        return
    console.print(f"[green]Exported[/green] {kid} → {path}")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("kengram_id", required=False)
@click.option(
    "--local",
    "local_only",
    is_flag=True,
    help="Skip API verification, check locally only.",
)
@_json_flag
def verify(kengram_id: str | None, local_only: bool, output_json: bool):
    """Verify a kEngram's merkle root against stored hashes."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        result = client.kengrams.verify(kid, local_only=local_only)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(json.dumps(result))
        return

    # Profile hash drift warning
    if result.get("profile_hash_status") == "drift":
        console.print(
            "[yellow]Warning:[/yellow] Ontology profile hash drift detected — "
            "profiles have changed since last annotation."
        )

    # Node-level output
    for node_uuid, node_info in result.get("nodes", {}).items():
        status = node_info.get("status", "unknown")
        if status == "ok":
            console.print(f"  {node_uuid[:12]}  [green]OK[/green]")
        elif status == "drift":
            stored = node_info.get("stored_hash", "")[:12]
            kg = node_info.get("kg_hash", "")[:12]
            console.print(
                f"  {node_uuid[:12]}  [yellow]DRIFT[/yellow]  stored={stored}.. kg={kg}.."
            )
        elif status == "not_in_kg":
            console.print(f"  {node_uuid[:12]}  [yellow]NOT IN KG[/yellow]")
        elif status == "canvas_modified":
            changes_str = ", ".join(node_info.get("changes", []))
            console.print(
                f"  {node_uuid[:12]}  [bold orange1]MODIFIED[/bold orange1]  {changes_str}"
            )
        elif status == "local_only":
            pass  # quiet for local-only

    canvas_modified = result.get("canvas_modified", 0)
    verified = result.get("status") == "verified"

    if canvas_modified:
        console.print(
            f"[bold orange1]{canvas_modified} node(s) modified on canvas — push to sync[/bold orange1]"
        )

    if verified and not canvas_modified:
        console.print(f"[green]Verified[/green] {result['id']}")
        console.print(f"  Merkle root: [dim]{result['merkle_root'][:16]}...[/dim]")
    elif canvas_modified and verified:
        console.print("[yellow]KG in sync[/yellow] but canvas has unpushed changes")
    elif not verified:
        console.print(f"[red]DRIFT DETECTED[/red] in {result['id']}")
        console.print(f"  Stored root:     [dim]{result['merkle_root'][:16]}...[/dim]")
        console.print(
            f"  Recomputed root: [dim]{result.get('recomputed_root', '')[:16]}...[/dim]"
        )

    # Plan structure
    plan = result.get("plan_structure", {})
    if plan:
        orphans = plan.get("orphan_tasks", [])
        cycles = plan.get("cycle_members", [])
        console.print("\n[bold]Plan structure:[/bold]")
        if orphans:
            console.print(
                f"  [yellow]Warning:[/yellow] {len(orphans)} task(s) not linked from Goal via DECOMPOSES_INTO"
            )
        if cycles:
            console.print(
                f"  [red]Error:[/red] DEPENDS_ON cycle detected involving {len(cycles)} task(s)"
            )
        if not orphans and not cycles:
            console.print("  [green]OK[/green] All tasks linked, no dependency cycles")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("name")
@click.option("--labels", default="Entity", help="Comma-separated labels.")
@click.option("--summary", default="", help="Entity summary.")
@_json_flag
def create(name: str, labels: str, summary: str, output_json: bool) -> None:
    """Create a new entity in the KG and pin it to the active kEngram."""
    client = _get_client()
    try:
        kengram_id = client.kengrams.get_active().id
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return

    label_list = [lb.strip() for lb in labels.split(",") if lb.strip()]
    attributes: dict[str, Any] = {"summary": summary} if summary else {}

    try:
        uuid = client.kg.create_entity(name, label_list, attributes)
    except APIError as e:
        msg = "Failed to create entity in KG."
        if output_json:
            _json_error(msg)
        _handle_error(e, json_mode=output_json)
        return

    # Pin with fresh data from KG
    try:
        result = client.kengrams.pin(kengram_id, uuid, fetch_from_kg=True)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    manifest = result["manifest"]
    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "created_and_pinned",
                    "uuid": uuid,
                    "name": name,
                    "merkle_root": manifest.merkle_root,
                }
            )
        )
        return
    console.print(f"[green]Created + Pinned[/green] {uuid}")
    console.print(f"  Name: {name}")
    console.print(f"  Merkle root: [dim]{manifest.merkle_root[:16]}...[/dim]")


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


@kengram.command()
@click.option("--id", "target_id", default=None, help="kEngram ID (default: active).")
@click.option(
    "--changes",
    "changes_json",
    default=None,
    help="JSON describing canvas modifications.",
)
@_json_flag
def push(target_id: str | None, changes_json: str | None, output_json: bool) -> None:
    """Push local-only nodes and edges to the canonical KG."""
    client = _get_client()
    try:
        kid = target_id or client.kengrams.get_active().id
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return

    changes = None
    if changes_json:
        try:
            changes = json.loads(changes_json)
        except json.JSONDecodeError:
            changes = {}

    try:
        result = client.kengrams.push(kid, changes=changes)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if result.get("stale_edges_dropped", 0) and not output_json:
        console.print(
            f"  [yellow]Dropped {result['stale_edges_dropped']} stale edge(s) referencing old UUIDs[/yellow]"
        )

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "pushed",
                    "kengram_id": result["kengram_id"],
                    "nodes_pushed": result["nodes_pushed"],
                    "nodes_skipped": result["nodes_skipped"],
                    "edges_pushed": result["edges_pushed"],
                    "edges_skipped": result["edges_skipped"],
                    "nodes_updated": result["nodes_updated"],
                    "nodes_created": result["nodes_created"],
                    "edges_created": result["edges_created"],
                    "merkle_root": result["merkle_root"],
                }
            )
        )
        return

    console.print(f"[green]Pushed[/green] {result['kengram_id']}")
    console.print(f"  Nodes pushed:  {result['nodes_pushed']}")
    console.print(f"  Nodes skipped: {result['nodes_skipped']}")
    console.print(f"  Edges pushed:  {result['edges_pushed']}")
    console.print(f"  Edges skipped: {result['edges_skipped']}")
    if result["nodes_updated"]:
        console.print(f"  Nodes updated: {result['nodes_updated']}")
    if result["nodes_created"]:
        console.print(f"  Nodes created: {result['nodes_created']}")
    if result["edges_created"]:
        console.print(f"  Edges created: {result['edges_created']}")
    console.print(f"  Merkle root: [dim]{result['merkle_root'][:16]}...[/dim]")


# ---------------------------------------------------------------------------
# repin
# ---------------------------------------------------------------------------


@kengram.command()
@click.argument("uuid")
@_json_flag
def repin(uuid: str, output_json: bool):
    """Re-fetch entity from KG and update hash in active kEngram."""
    client = _get_client()
    try:
        kid = client.kengrams.get_active().id
        result = client.kengrams.repin(kid, uuid)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "repinned",
                    "uuid": uuid,
                    "kengram_id": kid,
                    "changed": result["changed"],
                    "merkle_root": result["merkle_root"],
                }
            )
        )
        return
    if result["changed"]:
        console.print(f"[green]Repinned[/green] {uuid} — hash updated")
    else:
        console.print(f"[green]Repinned[/green] {uuid} — no change")
    console.print(f"  Merkle root: [dim]{result['merkle_root'][:16]}...[/dim]")


# ---------------------------------------------------------------------------
# import-owl
# ---------------------------------------------------------------------------


@kengram.command(name="import-owl")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--profile", "profile_id", required=True, help="Profile ID for inverted mappings."
)
@click.option(
    "--into", "kengram_id", default=None, help="Target kEngram ID (default: active)."
)
@_json_flag
def import_owl(
    file: str, profile_id: str, kengram_id: str | None, output_json: bool
) -> None:
    """Import entities from an OWL/RDF file using a profile's inverted mappings."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        result = client.kengrams.import_owl(kid, file, profile_id)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "imported",
                    "kengram_id": result["kengram_id"],
                    "nodes_added": result["nodes_added"],
                    "source_file": file,
                    "merkle_root": result["merkle_root"],
                }
            )
        )
        return
    console.print(
        f"[green]Imported[/green] {result['nodes_added']} entity/entities from {file}"
    )
    console.print(f"  kEngram: {result['kengram_id']}")
    console.print(f"  Merkle root: [dim]{result['merkle_root'][:16]}...[/dim]")


# ---------------------------------------------------------------------------
# Register profile subcommand group
# ---------------------------------------------------------------------------

from bonfires.kengram.profile_commands import profile  # noqa: E402

kengram.add_command(profile)
