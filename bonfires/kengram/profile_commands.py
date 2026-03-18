"""CLI commands for OWL ontology profile management."""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires.config import get_config
from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.storage import KEngramStorage

console = Console()

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


def _resolve_manifest(
    store: KEngramStorage, kengram_id: str | None, *, json_mode: bool = False,
) -> KEngramManifest | None:
    """Load manifest by ID or fall back to active."""
    if kengram_id:
        manifest = store.load(kengram_id)
        if not manifest:
            msg = f"kEngram '{kengram_id}' not found."
            if json_mode:
                _json_error(msg)
            console.print(f"[red]{msg}[/red]")
            return None
        return manifest
    return _get_active_manifest(store, json_mode=json_mode)


@click.group()
def profile() -> None:
    """Manage OWL ontology profiles for kEngrams."""


@profile.command(name="new")
@click.argument("name")
@click.option("--namespace", "namespaces", multiple=True, help="prefix=uri (repeatable).")
@_json_flag
def profile_new(name: str, namespaces: tuple[str, ...], output_json: bool) -> None:
    """Create a new empty ontology profile."""
    from bonfires.kengram.ontology_profile import OntologyProfile

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

    prof = OntologyProfile.create(name=name, namespaces=ns_dict or None)
    store = _get_storage()
    path = store.save_profile(prof)

    if output_json:
        click.echo(json.dumps({
            "status": "created",
            "id": prof.id,
            "name": prof.name,
            "path": str(path),
        }))
        return
    console.print(f"[green]Created[/green] profile {prof.id}")
    console.print(f"  Name: {prof.name}")
    console.print(f"  Path: [dim]{path}[/dim]")


@profile.command(name="list")
@_json_flag
def profile_list(output_json: bool) -> None:
    """List all ontology profiles."""
    store = _get_storage()
    items = store.list_profiles()

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
    store = _get_storage()
    prof = store.load_profile(profile_id)
    if not prof:
        msg = f"Profile '{profile_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    if output_json:
        click.echo(json.dumps(prof.to_dict()))
        return

    # Namespaces
    ns_lines = "\n".join(f"  {prefix}: {uri}" for prefix, uri in prof.namespaces.items())

    # Class map
    class_lines: list[str] = []
    for label, mapping in prof.class_map.items():
        owl_class = mapping.get("owl_class", "")
        class_lines.append(f"  {label} -> {owl_class}")
    class_str = "\n".join(class_lines) if class_lines else "  [dim](none)[/dim]"

    # Object property map
    obj_lines: list[str] = []
    for edge_name, mapping in prof.object_property_map.items():
        owl_prop = mapping.get("owl_property", "")
        obj_lines.append(f"  {edge_name} -> {owl_prop}")
    obj_str = "\n".join(obj_lines) if obj_lines else "  [dim](none)[/dim]"

    # Datatype property map
    dt_lines: list[str] = []
    for attr_name, mapping in prof.datatype_property_map.items():
        owl_prop = mapping.get("owl_property", "")
        dt_lines.append(f"  {attr_name} -> {owl_prop}")
    dt_str = "\n".join(dt_lines) if dt_lines else "  [dim](none)[/dim]"

    console.print(Panel(
        f"[bold]{prof.name}[/bold] (v{prof.version})\n"
        f"ID: [dim]{prof.id}[/dim]\n\n"
        f"[bold]Namespaces:[/bold]\n{ns_lines}\n\n"
        f"[bold]Class Map:[/bold]\n{class_str}\n\n"
        f"[bold]Object Property Map:[/bold]\n{obj_str}\n\n"
        f"[bold]Datatype Property Map:[/bold]\n{dt_str}",
        title="Ontology Profile",
        border_style="bright_blue",
    ))


@profile.command(name="attach")
@click.argument("profile_id")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_attach(profile_id: str, kengram_id: str | None, output_json: bool) -> None:
    """Attach an ontology profile to a kEngram manifest."""
    from bonfires.kengram.ontology_profile import compute_profile_hash

    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    prof = store.load_profile(profile_id)
    if not prof:
        msg = f"Profile '{profile_id}' not found."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    if profile_id in manifest.ontology_profiles:
        msg = f"Profile '{profile_id}' is already attached to {manifest.id}."
        if output_json:
            _json_error(msg)
        console.print(f"[yellow]{msg}[/yellow]")
        return

    manifest.ontology_profiles.append(profile_id)
    manifest.profile_hash = compute_profile_hash(
        manifest.ontology_profiles, store.profiles_dir,
    )
    store.save(manifest)

    if output_json:
        click.echo(json.dumps({
            "status": "attached",
            "profile_id": profile_id,
            "kengram_id": manifest.id,
            "profile_hash": manifest.profile_hash,
        }))
        return
    console.print(f"[green]Attached[/green] {profile_id} to {manifest.id}")
    console.print(f"  Profile hash: [dim]{manifest.profile_hash[:16]}...[/dim]")


@profile.command(name="detach")
@click.argument("profile_id")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_detach(profile_id: str, kengram_id: str | None, output_json: bool) -> None:
    """Remove an ontology profile from a kEngram manifest."""
    from bonfires.kengram.ontology_profile import compute_profile_hash

    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    if profile_id not in manifest.ontology_profiles:
        msg = f"Profile '{profile_id}' is not attached to {manifest.id}."
        if output_json:
            _json_error(msg)
        console.print(f"[yellow]{msg}[/yellow]")
        return

    manifest.ontology_profiles.remove(profile_id)
    manifest.profile_hash = compute_profile_hash(
        manifest.ontology_profiles, store.profiles_dir,
    )
    store.save(manifest)

    if output_json:
        click.echo(json.dumps({
            "status": "detached",
            "profile_id": profile_id,
            "kengram_id": manifest.id,
            "profile_hash": manifest.profile_hash,
        }))
        return
    console.print(f"[green]Detached[/green] {profile_id} from {manifest.id}")
    console.print(f"  Profile hash: [dim]{manifest.profile_hash[:16]}...[/dim]")


@profile.command(name="validate")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_validate(kengram_id: str | None, output_json: bool) -> None:
    """Validate a kEngram against its attached ontology profiles."""
    from bonfires.kengram.ontology_pipeline import annotate_manifest, validate_graph
    from bonfires.kengram.ontology_profile import compose_profiles

    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    if not manifest.ontology_profiles:
        msg = "No ontology profiles attached. Use `profile attach` first."
        if output_json:
            _json_error(msg)
        console.print(f"[yellow]{msg}[/yellow]")
        return

    profiles = store.load_profiles_for_manifest(manifest)
    if not profiles:
        msg = "Could not load any attached profiles."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    composed = compose_profiles(profiles)
    violations = validate_graph(manifest, composed)
    annotate_manifest(manifest, composed, violations)
    store.save(manifest)

    if output_json:
        click.echo(json.dumps({
            "status": "validated",
            "kengram_id": manifest.id,
            "violation_count": len(violations),
            "violations": violations,
        }))
        return

    if not violations:
        console.print(f"[green]No violations[/green] in {manifest.id}")
        return

    # Group violations by entity
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for v in violations:
        key = v["entity_uuid"]
        by_entity.setdefault(key, []).append(v)

    console.print(f"[yellow]{len(violations)} violation(s)[/yellow] in {manifest.id}\n")
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
    from bonfires.kengram.ontology_pipeline import extract_vocabulary, identify_profiles

    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    vocabulary = extract_vocabulary(manifest)
    all_profiles_data = store.list_profiles()
    if not all_profiles_data:
        msg = "No profiles available to suggest."
        if output_json:
            _json_error(msg)
        console.print("[dim]No profiles available.[/dim]")
        return

    from bonfires.kengram.ontology_profile import OntologyProfile

    all_profiles = [
        p for pid in [d["id"] for d in all_profiles_data]
        if (p := store.load_profile(pid)) is not None
    ]

    scored = identify_profiles(vocabulary, all_profiles)

    if output_json:
        click.echo(json.dumps({
            "kengram_id": manifest.id,
            "suggestions": [
                {"profile_id": p.id, "name": p.name, "score": round(s, 4)}
                for p, s in scored
            ],
        }))
        return

    table = Table(title="Profile Suggestions", title_style="bold")
    table.add_column("Profile ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Score", justify="right")
    for p, score in scored:
        color = "green" if score >= 0.5 else ("yellow" if score > 0 else "dim")
        table.add_row(p.id, p.name, f"[{color}]{score:.2%}[/{color}]")
    console.print(table)


@profile.command(name="match")
@click.option("--ontology", "ontology_id", required=True, help="Ontology ID to match against.")
@click.option("--threshold", default=0.7, type=float, help="Similarity threshold (default: 0.7).")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_match(
    ontology_id: str, threshold: float, kengram_id: str | None, output_json: bool,
) -> None:
    """Vector match labels against an ontology and generate a profile."""
    from bonfires.kengram import kg_client
    from bonfires.kengram.ontology_profile import OntologyProfile

    cfg = get_config()
    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    bonfire_id = cfg["bonfire_id"]

    if not output_json:
        console.print(f"Matching labels against ontology [bold]{ontology_id}[/bold]...")

    matches = kg_client.match_labels(cfg, bonfire_id, ontology_id, threshold)
    if matches is None:
        msg = "Backend label matching failed."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    if not output_json:
        console.print(f"  Found {len(matches)} match(es)")

    result = kg_client.generate_profile(cfg, bonfire_id, ontology_id, threshold)
    if result is None:
        msg = "Backend profile generation failed."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    prof = OntologyProfile.from_dict(result) if "id" in result else OntologyProfile.create(
        name=f"matched-{ontology_id}",
        namespaces=result.get("namespaces"),
        class_map=result.get("class_map"),
        object_property_map=result.get("object_property_map"),
        datatype_property_map=result.get("datatype_property_map"),
    )
    path = store.save_profile(prof)

    if output_json:
        click.echo(json.dumps({
            "status": "generated",
            "profile_id": prof.id,
            "matches": len(matches),
            "path": str(path),
        }))
        return
    console.print(f"[green]Generated[/green] profile {prof.id}")
    console.print(f"  Path: [dim]{path}[/dim]")


@profile.command(name="gaps")
@click.argument("kengram_id", required=False)
@_json_flag
def profile_gaps(kengram_id: str | None, output_json: bool) -> None:
    """Extract and display structured gaps from ontology validation."""
    from bonfires.kengram.ontology_pipeline import (
        annotate_manifest,
        extract_gaps,
        validate_graph,
    )
    from bonfires.kengram.ontology_profile import compose_profiles

    store = _get_storage()
    manifest = _resolve_manifest(store, kengram_id, json_mode=output_json)
    if not manifest:
        return

    if not manifest.ontology_profiles:
        msg = "No ontology profiles attached. Use `profile attach` first."
        if output_json:
            _json_error(msg)
        console.print(f"[yellow]{msg}[/yellow]")
        return

    profiles = store.load_profiles_for_manifest(manifest)
    if not profiles:
        msg = "Could not load any attached profiles."
        if output_json:
            _json_error(msg)
        console.print(f"[red]{msg}[/red]")
        return

    composed = compose_profiles(profiles)
    violations = validate_graph(manifest, composed)
    annotate_manifest(manifest, composed, violations)
    store.save(manifest)
    gaps = extract_gaps(manifest)

    if output_json:
        click.echo(json.dumps({
            "kengram_id": manifest.id,
            "gap_count": len(gaps),
            "gaps": gaps,
        }))
        return

    if not gaps:
        console.print(f"[green]No gaps[/green] in {manifest.id}")
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
