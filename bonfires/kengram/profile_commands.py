"""CLI commands for OWL ontology profile management.

Thin Click shell — business logic lives in bonfires.sdk.ontology.
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
from bonfires.sdk.exceptions import BonfiresError, ConfigError, NotFoundError

console = Console()

_json_flag = click.option("--json", "output_json", is_flag=True, help="Output as JSON.")


def _json_error(msg: str) -> NoReturn:
    click.echo(json.dumps({"error": msg}))
    sys.exit(1)


def _get_client() -> BonfiresClient:
    try:
        return BonfiresClient()
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


def _handle_error(e: BonfiresError, *, json_mode: bool = False) -> None:
    msg = str(e)
    if json_mode:
        _json_error(msg)
    console.print(f"[red]{msg}[/red]")
    sys.exit(1)


@click.group()
def profile() -> None:
    """Manage OWL ontology profiles for kEngrams."""


@profile.command(name="new")
@click.argument("name")
@click.option(
    "--namespace", "namespaces", multiple=True, help="prefix=uri (repeatable)."
)
@_json_flag
def profile_new(name: str, namespaces: tuple[str, ...], output_json: bool) -> None:
    """Create a new empty ontology profile."""
    ns_dict: dict[str, str] = {}
    for entry in namespaces:
        if "=" not in entry:
            msg = f"Invalid namespace format: '{entry}'. Expected prefix=uri."
            if output_json:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return
        prefix, uri = entry.split("=", 1)
        ns_dict[prefix.strip()] = uri.strip()

    client = _get_client()
    prof = client.ontology.create_profile(name, namespaces=ns_dict or None)

    if output_json:
        click.echo(json.dumps({"status": "created", "id": prof.id, "name": prof.name}))
        return
    console.print(f"[green]Created[/green] profile {prof.id}")
    console.print(f"  Name: {prof.name}")


@profile.command(name="list")
@_json_flag
def profile_list(output_json: bool) -> None:
    """List all ontology profiles."""
    client = _get_client()
    items = client.ontology.list_profiles()

    if output_json:
        click.echo(json.dumps({"profiles": items}))
        return

    if not items:
        console.print("[dim]No profiles found.[/dim]")
        return

    table = Table(title="Ontology Profiles", title_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Version")
    table.add_column("Namespaces")
    for item in items:
        table.add_row(
            item["id"],
            item["name"],
            item.get("version", ""),
            ", ".join(item.get("namespaces", [])),
        )
    console.print(table)


@profile.command(name="show")
@click.argument("profile_id")
@_json_flag
def profile_show(profile_id: str, output_json: bool) -> None:
    """Show full profile details including mappings."""
    client = _get_client()
    try:
        prof = client.ontology.get_profile(profile_id)
    except NotFoundError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(json.dumps(prof.to_dict()))
        return

    ns_lines = "\n".join(
        f"  {prefix}: {uri}" for prefix, uri in prof.namespaces.items()
    )
    class_lines: list[str] = []
    for label, mapping in prof.class_map.items():
        owl_class = mapping.get("owl_class", "")
        class_lines.append(f"  {label} -> {owl_class}")
    class_str = "\n".join(class_lines) if class_lines else "  [dim](none)[/dim]"

    obj_lines: list[str] = []
    for edge_name, mapping in prof.object_property_map.items():
        owl_prop = mapping.get("owl_property", "")
        obj_lines.append(f"  {edge_name} -> {owl_prop}")
    obj_str = "\n".join(obj_lines) if obj_lines else "  [dim](none)[/dim]"

    dt_lines: list[str] = []
    for attr_name, mapping in prof.datatype_property_map.items():
        owl_prop = mapping.get("owl_property", "")
        dt_lines.append(f"  {attr_name} -> {owl_prop}")
    dt_str = "\n".join(dt_lines) if dt_lines else "  [dim](none)[/dim]"

    console.print(
        Panel(
            f"[bold]{prof.name}[/bold] (v{prof.version})\n"
            f"ID: [dim]{prof.id}[/dim]\n\n"
            f"[bold]Namespaces:[/bold]\n{ns_lines}\n\n"
            f"[bold]Class Map:[/bold]\n{class_str}\n\n"
            f"[bold]Object Property Map:[/bold]\n{obj_str}\n\n"
            f"[bold]Datatype Property Map:[/bold]\n{dt_str}",
            title="Ontology Profile",
            border_style="bright_blue",
        )
    )


@profile.command(name="attach")
@click.argument("profile_id")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_attach(profile_id: str, kengram_id: str | None, output_json: bool) -> None:
    """Attach an ontology profile to a kEngram manifest."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        manifest = client.ontology.attach_profile(kid, profile_id)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "attached",
                    "profile_id": profile_id,
                    "kengram_id": manifest.id,
                    "profile_hash": manifest.profile_hash,
                }
            )
        )
        return
    console.print(f"[green]Attached[/green] {profile_id} to {manifest.id}")
    console.print(f"  Profile hash: [dim]{manifest.profile_hash[:16]}...[/dim]")


@profile.command(name="detach")
@click.argument("profile_id")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_detach(profile_id: str, kengram_id: str | None, output_json: bool) -> None:
    """Remove an ontology profile from a kEngram manifest."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        manifest = client.ontology.detach_profile(kid, profile_id)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "detached",
                    "profile_id": profile_id,
                    "kengram_id": manifest.id,
                    "profile_hash": manifest.profile_hash,
                }
            )
        )
        return
    console.print(f"[green]Detached[/green] {profile_id} from {manifest.id}")
    console.print(f"  Profile hash: [dim]{manifest.profile_hash[:16]}...[/dim]")


@profile.command(name="validate")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_validate(kengram_id: str | None, output_json: bool) -> None:
    """Validate a kEngram against its attached ontology profiles."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        result = client.ontology.validate(kid)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    violations = result["violations"]
    if output_json:
        click.echo(json.dumps(result))
        return

    if not violations:
        console.print(f"[green]No violations[/green] in {result['kengram_id']}")
        return

    by_entity: dict[str, list[dict[str, Any]]] = {}
    for v in violations:
        key = v["entity_uuid"]
        by_entity.setdefault(key, []).append(v)

    console.print(
        f"[yellow]{len(violations)} violation(s)[/yellow] in {result['kengram_id']}\n"
    )
    for entity_uuid, entity_violations in by_entity.items():
        entity_name = entity_violations[0].get("entity_name", entity_uuid[:12])
        console.print(f"  [bold]{entity_name}[/bold] ({entity_uuid[:12]})")
        for v in entity_violations:
            console.print(f"    [yellow]{v['violation']}[/yellow]: {v['message']}")
        console.print()


@profile.command(name="suggest")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_suggest(kengram_id: str | None, output_json: bool) -> None:
    """Score available profiles against a kEngram's vocabulary."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        scored = client.ontology.suggest_profiles(kid)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(json.dumps({"kengram_id": kid, "suggestions": scored}))
        return

    if not scored:
        console.print("[dim]No profiles available.[/dim]")
        return

    table = Table(title="Profile Suggestions", title_style="bold")
    table.add_column("Profile ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Score", justify="right")
    for item in scored:
        score = item["score"]
        color = "green" if score >= 0.5 else ("yellow" if score > 0 else "dim")
        table.add_row(
            item["profile_id"], item["name"], f"[{color}]{score:.2%}[/{color}]"
        )
    console.print(table)


@profile.command(name="match")
@click.option(
    "--ontology", "ontology_id", required=True, help="Ontology ID to match against."
)
@click.option(
    "--threshold", default=0.7, type=float, help="Similarity threshold (default: 0.7)."
)
@click.argument("kengram_id", required=False)
@_json_flag
def profile_match(
    ontology_id: str,
    threshold: float,
    kengram_id: str | None,
    output_json: bool,
) -> None:
    """Vector match labels against an ontology and generate a profile."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id

        if not output_json:
            console.print(
                f"Matching labels against ontology [bold]{ontology_id}[/bold]..."
            )

        matches = client.ontology.match_labels(ontology_id, threshold)
        if not output_json:
            console.print(f"  Found {len(matches)} match(es)")

        prof = client.ontology.match_and_generate(kid, ontology_id, threshold)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "status": "generated",
                    "profile_id": prof.id,
                    "matches": len(matches),
                }
            )
        )
        return
    console.print(f"[green]Generated[/green] profile {prof.id}")


@profile.command(name="gaps")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_gaps(kengram_id: str | None, output_json: bool) -> None:
    """Extract and display structured gaps from ontology validation."""
    client = _get_client()
    try:
        kid = kengram_id or client.kengrams.get_active().id
        gaps = client.ontology.extract_gaps(kid)
    except BonfiresError as e:
        _handle_error(e, json_mode=output_json)
        return

    if output_json:
        click.echo(
            json.dumps({"kengram_id": kid, "gap_count": len(gaps), "gaps": gaps})
        )
        return

    if not gaps:
        console.print(f"[green]No gaps[/green] in {kid}")
        return

    table = Table(title="Ontology Gaps", title_style="bold")
    table.add_column("Entity", style="bold")
    table.add_column("Gap Type")
    table.add_column("Property", style="dim")
    table.add_column("Description")
    table.add_column("Expected Type", style="dim")
    for gap in gaps:
        table.add_row(
            gap["entity_name"],
            gap["gap_type"],
            gap["property"],
            gap["property_description"],
            gap["expected_type"],
        )
    console.print(table)
