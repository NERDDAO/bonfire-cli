#!/usr/bin/env python3
"""Bonfire CLI — Beautiful terminal interface for the Bonfires API."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text

# Load .env from the script's directory, not CWD
_script_dir = Path(__file__).resolve().parent
load_dotenv(_script_dir / ".env")

console = Console()


# --- Config ---

def get_config():
    """Load and validate configuration from environment."""
    cfg = {
        "api_url": os.environ.get("BONFIRE_API_URL", "https://tnt-v2.api.bonfires.ai"),
        "bonfire_id": os.environ.get("BONFIRE_ID"),
        "agent_id": os.environ.get("BONFIRE_AGENT_ID"),
        "api_key": os.environ.get("BONFIRE_API_KEY"),
    }
    missing = [k for k, v in cfg.items() if v is None and k != "api_url"]
    if missing:
        console.print(f"[red]Missing config: {', '.join(missing)}[/red]")
        console.print(f"Set them in {_script_dir / '.env'} or as environment variables.")
        sys.exit(1)
    return cfg


# --- API Client ---

def api_headers(cfg):
    """Return common auth headers."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "X-Bonfire-Id": cfg["bonfire_id"],
        "X-Agent-Id": cfg["agent_id"],
    }


def api_post(cfg, path, body):
    """POST to the Bonfires API and return parsed JSON."""
    url = f"{cfg['api_url']}{path}"
    try:
        resp = requests.post(url, json=body, headers=api_headers(cfg), timeout=30)
    except requests.RequestException as e:
        console.print(Panel(str(e), title="Connection Error", border_style="red"))
        sys.exit(1)
    if not resp.ok:
        console.print(Panel(resp.text[:500], title=f"API Error {resp.status_code}", border_style="red"))
        sys.exit(1)
    return resp.json()


def api_get(cfg, path, params=None):
    """GET from the Bonfires API and return parsed JSON."""
    url = f"{cfg['api_url']}{path}"
    try:
        resp = requests.get(url, params=params, headers=api_headers(cfg), timeout=30)
    except requests.RequestException as e:
        console.print(Panel(str(e), title="Connection Error", border_style="red"))
        sys.exit(1)
    if not resp.ok:
        console.print(Panel(resp.text[:500], title=f"API Error {resp.status_code}", border_style="red"))
        sys.exit(1)
    return resp.json()


# --- Formatting Helpers ---

LABEL_COLORS = {
    "Entity": "dim",
    "TaxonomyLabel": "cyan",
    "Update": "yellow",
}

ACTION_COLORS = {
    "do_nothing": "green",
    "search": "yellow",
    "fetch": "yellow",
    "expand": "yellow",
}


def truncate(text, length=120):
    """Truncate text to length with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:length] + "..." if len(text) > length else text


def format_labels(labels):
    """Render entity labels as colored badges."""
    if not labels:
        return Text("")
    parts = Text()
    for i, label in enumerate(labels):
        color = LABEL_COLORS.get(label, "white")
        if i > 0:
            parts.append(" ")
        parts.append(label, style=color)
    return parts


def format_episodes(episodes):
    """Render episodes as a rich Table."""
    if not episodes:
        return
    table = Table(title="Episodes", title_style="bold magenta")
    table.add_column("Name", style="bold", max_width=40)
    table.add_column("Date", style="green", max_width=12)
    table.add_column("Summary", max_width=60)
    for ep in episodes:
        name = ep.get("name", "—")
        date = (ep.get("valid_at") or ep.get("created_at", ""))[:10]
        content = ep.get("content", {})
        summary = content.get("content", "") if isinstance(content, dict) else str(content)
        table.add_row(truncate(name, 40), date, truncate(summary))
    console.print(table)


def format_entities(entities):
    """Render entities as a rich Table."""
    if not entities:
        return
    table = Table(title="Entities", title_style="bold cyan")
    table.add_column("Name", style="bold", max_width=30)
    table.add_column("Labels", max_width=20)
    table.add_column("Summary", max_width=60)
    for ent in entities:
        name = ent.get("name", "—")
        labels = format_labels(ent.get("labels", []))
        summary = truncate(ent.get("summary", ""), 120)
        table.add_row(name, labels, summary)
    console.print(table)


def format_edges(edges, entities=None):
    """Render edges as a Tree grouped by source entity."""
    if not edges:
        return
    # Build entity name lookup
    entity_map = {}
    if entities:
        for ent in entities:
            entity_map[ent.get("uuid", "")] = ent.get("name", ent.get("uuid", "?"))

    # Group edges by source
    grouped = {}
    for edge in edges:
        src = entity_map.get(edge.get("source_node_uuid", ""), edge.get("source_node_uuid", "?")[:8])
        grouped.setdefault(src, []).append(edge)

    tree = Tree("[bold]Relationships[/bold]")
    for src, src_edges in grouped.items():
        branch = tree.add(f"[bold]{src}[/bold]")
        for edge in src_edges:
            rel = edge.get("name", "RELATED_TO")
            tgt = entity_map.get(edge.get("target_node_uuid", ""), edge.get("target_node_uuid", "?")[:8])
            fact = truncate(edge.get("fact", ""), 80)
            label = f"[yellow]{rel}[/yellow] -> [cyan]{tgt}[/cyan]"
            if fact:
                label += f"\n  [dim]{fact}[/dim]"
            branch.add(label)
    console.print(tree)


def format_graph(data):
    """Render all graph data found in a response.

    Handles both "entities" and "nodes" keys (they are synonymous in Bonfires).
    """
    episodes = data.get("episodes", [])
    entities = data.get("entities", []) or data.get("nodes", [])
    edges = data.get("edges", [])
    if episodes:
        format_episodes(episodes)
    if entities:
        format_entities(entities)
    if edges:
        format_edges(edges, entities)
    if not episodes and not entities and not edges:
        console.print("[dim]No graph data.[/dim]")


def format_chat_response(data):
    """Render a chat API response."""
    reply = data.get("reply", "")
    if reply:
        console.print(Panel(reply, title="Bonfire Reply", border_style="bright_blue", padding=(1, 2)))

    # Graph action badge
    action = data.get("graph_action", "")
    if action:
        color = ACTION_COLORS.get(action, "red")
        console.print(f"  Graph Action: [{color}]{action}[/{color}]")

    # Errors
    errors = data.get("errors", [])
    if errors:
        for err in errors:
            console.print(f"  [red]Error: {err}[/red]")

    # Graph data (if present — chat nests it under "graph_data")
    graph_data = data.get("graph_data")
    if graph_data:
        console.print()
        format_graph(graph_data)


def format_delve_response(data, query=""):
    """Render a delve API response.

    Delve responses have episodes/entities/edges at top level (not nested).
    """
    num = data.get("num_results", 0)
    console.print(f'\n[bold]Delve:[/bold] "{query}" — [cyan]{num} results[/cyan]\n')
    format_graph(data)

    # Metrics
    metrics = data.get("metrics", {})
    duration = metrics.get("duration_ms")
    if duration:
        console.print(f"\n[dim]Search completed in {duration:.0f}ms[/dim]")


def read_json_stdin():
    """Read and parse JSON from stdin."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON:[/red] {e}")
        sys.exit(1)


# --- CLI ---

@click.group()
def cli():
    """Bonfire CLI — Beautiful terminal interface for the Bonfires API."""
    pass


@cli.command()
@click.argument("message")
def chat(message):
    """Send a message to a Bonfire agent."""
    cfg = get_config()
    body = {
        "message": message,
        "agent_id": cfg["agent_id"],
        "bonfire_id": cfg["bonfire_id"],
        "chat_history": [],
        "graph_mode": "adaptive",
    }
    data = api_post(cfg, f"/agents/{cfg['agent_id']}/chat", body)
    format_chat_response(data)


@cli.command()
@click.argument("query")
@click.option("-n", "--num-results", default=10, help="Number of results to return.")
def delve(query, num_results):
    """Search the Bonfires knowledge graph."""
    cfg = get_config()
    body = {
        "query": query,
        "bonfire_id": cfg["bonfire_id"],
        "num_results": num_results,
        "agent_id": cfg["agent_id"],
    }
    data = api_post(cfg, "/delve", body)
    format_delve_response(data, query)


@cli.command()
def agents():
    """List agents for the configured bonfire."""
    cfg = get_config()
    data = api_get(cfg, "/agents", params={"bonfire_id": cfg["bonfire_id"]})
    agents_list = data if isinstance(data, list) else data.get("agents", data.get("data", []))
    table = Table(title="Agents", title_style="bold green")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Description", max_width=50)
    for a in agents_list:
        table.add_row(
            a.get("name", "—"),
            a.get("_id", a.get("id", "—")),
            truncate(a.get("description", ""), 50),
        )
    console.print(table)


@cli.command(name="bonfires")
def list_bonfires():
    """List all bonfires."""
    cfg = get_config()
    data = api_get(cfg, "/bonfires")
    bonfires_list = data if isinstance(data, list) else data.get("bonfires", data.get("data", []))
    table = Table(title="Bonfires", title_style="bold green")
    table.add_column("Name", style="bold")
    table.add_column("ID", style="dim")
    for b in bonfires_list:
        table.add_row(
            b.get("name", "—"),
            b.get("_id", b.get("id", "—")),
        )
    console.print(table)


@cli.command(name="format-chat")
def format_chat_cmd():
    """Format a chat response from stdin (no API call)."""
    data = read_json_stdin()
    format_chat_response(data)


@cli.command(name="format-delve")
@click.option("-q", "--query", default="", help="Original query (for display header).")
def format_delve_cmd(query):
    """Format a delve response from stdin (no API call)."""
    data = read_json_stdin()
    format_delve_response(data, query=query or data.get("query", ""))


@cli.command()
@click.argument("file", required=False, type=click.Path(exists=True))
def graph(file):
    """Render graph data from a JSON file or stdin."""
    if file:
        with open(file) as f:
            data = json.load(f)
    else:
        data = read_json_stdin()
    format_graph(data)


@cli.command()
@click.argument("message")
@click.option("--title", default=None, help="Title for the ingested document.")
@click.option("--ingest", is_flag=True, help="Also ingest as a document (for large artifacts like markdown files).")
def sync(message, title, ingest):
    """Push context to the Bonfires knowledge graph via stack + ingest."""
    cfg = get_config()

    # Derive chatId from git context
    chat_id = _git_chat_id()
    repo = chat_id.split(":")[0] if ":" in chat_id else "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1: Stack add
    console.print("[bold]1/2[/bold] Pushing to stack...", end=" ")
    stack_body = {
        "message": {
            "userId": "claude-code",
            "chatId": chat_id,
            "role": "assistant",
            "text": message,
            "timestamp": timestamp,
        },
        "metadata": {
            "type": "memory-sync",
            "source": "bonfire-cli",
            "repo": repo,
        },
    }
    stack_resp = api_post(cfg, f"/agents/{cfg['agent_id']}/stack/add", stack_body)
    if stack_resp.get("success"):
        console.print("[green]OK[/green]")
    else:
        console.print("[red]FAILED[/red]")
        console.print(stack_resp)
        return

    # Step 2: Stack process
    console.print("[bold]2/2[/bold] Processing stack...", end=" ")
    api_post(cfg, f"/agents/{cfg['agent_id']}/stack/process", {})
    console.print("[green]OK[/green]")

    # Optional: Ingest as document (for large artifacts like md files)
    if ingest:
        console.print("[bold]+[/bold] Ingesting document...", end=" ")
        doc_title = title or f"Bonfire Sync — {truncate(message, 60)}"
        ingest_body = {
            "content": message,
            "title": doc_title,
            "bonfire_id": cfg["bonfire_id"],
            "agent_id": cfg["agent_id"],
            "metadata": {
                "type": "memory-sync",
                "source": "bonfire-cli",
                "repo": repo,
            },
        }
        ingest_resp = api_post(cfg, "/ingest_content", ingest_body)
        doc_id = ingest_resp.get("document_id", "unknown")
        console.print(f"[green]OK[/green] (doc: [dim]{doc_id}[/dim])")

    console.print(Panel(
        f"[bold]Context synced[/bold]\n\n"
        f"  Chat ID: [cyan]{chat_id}[/cyan]\n"
        f"  Repo: [cyan]{repo}[/cyan]\n"
        f"  Message: {truncate(message, 80)}",
        title="Sync Complete",
        border_style="green",
    ))


def _git_chat_id():
    """Derive a chatId from git repo name + branch."""
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        repo = Path(toplevel.stdout.strip()).name if toplevel.returncode == 0 else "unknown"
        br = branch.stdout.strip() if branch.returncode == 0 else "unknown"
        return f"{repo}:{br}"
    except Exception:
        return "bonfire-cli:unknown"


if __name__ == "__main__":
    cli()
