"""Bonfire CLI — Beautiful terminal interface for the Bonfires API."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires import __version__
from bonfires.api import api_get, api_post
from bonfires.config import CONFIG_DIR, CONFIG_FILE, DEFAULT_API_URL, get_config
from bonfires.kengram.commands import kengram as kengram_group
from bonfires.formatting import (
    format_chat_response,
    format_delve_response,
    format_graph,
    truncate,
)

console = Console()


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
@click.version_option(version=__version__, prog_name="bonfires")
def cli():
    """Bonfires CLI — Terminal interface for the Bonfires AI API."""


@cli.command()
@click.option("--api-url", default=None, help="API base URL.")
@click.option("--api-key", default=None, help="API key (skip interactive prompt).")
@click.option("--bonfire-id", default=None, help="Bonfire ID (skip interactive prompt).")
@click.option("--agent-id", default=None, help="Agent ID (skip interactive prompt).")
def init(api_url, api_key, bonfire_id, agent_id):
    """Set up Bonfires CLI configuration.

    Walks you through connecting to the Bonfires API and saves your
    credentials to ~/.config/bonfires/config.env.
    """
    console.print()
    console.print(Panel.fit(
        "[bold bright_blue]Bonfires CLI[/bold bright_blue]\n"
        "[dim]Terminal interface for the Bonfires AI knowledge graph[/dim]",
        border_style="bright_blue",
    ))
    console.print()

    # API URL
    if not api_url:
        api_url = console.input(
            f"  API URL [dim]({DEFAULT_API_URL})[/dim]: "
        ).strip() or DEFAULT_API_URL
    console.print(f"  [dim]Using:[/dim] {api_url}")

    # API Key
    if not api_key:
        console.print()
        console.print("  Get your API key from the Bonfires dashboard.")
        api_key = console.input("  API Key: ").strip()
        if not api_key:
            console.print("[red]  API key is required.[/red]")
            sys.exit(1)

    # Test connection and list bonfires
    console.print()
    console.print("  [dim]Testing connection...[/dim]", end=" ")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    try:
        resp = requests.get(f"{api_url}/bonfires", headers=headers, timeout=10)
        if not resp.ok:
            console.print(f"[red]Failed ({resp.status_code})[/red]")
            console.print(f"  [red]{resp.text[:200]}[/red]")
            sys.exit(1)
        console.print("[green]OK[/green]")
    except requests.RequestException as e:
        console.print(f"[red]Failed[/red]")
        console.print(f"  [red]{e}[/red]")
        sys.exit(1)

    # Pick bonfire
    if not bonfire_id:
        bonfires_data = resp.json()
        bonfires_list = bonfires_data if isinstance(bonfires_data, list) else bonfires_data.get("bonfires", bonfires_data.get("data", []))

        if bonfires_list:
            console.print()
            table = Table(title="Your Bonfires", title_style="bold", show_lines=False, padding=(0, 2))
            table.add_column("#", style="bold bright_blue", width=4)
            table.add_column("Name", style="bold")
            table.add_column("ID", style="dim")
            for i, b in enumerate(bonfires_list, 1):
                table.add_row(str(i), b.get("name", "—"), b.get("_id", b.get("id", "—")))
            console.print(table)
            console.print()

            choice = console.input(f"  Select bonfire [dim](1-{len(bonfires_list)})[/dim]: ").strip()
            try:
                idx = int(choice) - 1
                selected = bonfires_list[idx]
                bonfire_id = selected.get("_id", selected.get("id"))
                console.print(f"  [dim]Selected:[/dim] {selected.get('name', bonfire_id)}")
            except (ValueError, IndexError):
                console.print("[red]  Invalid selection.[/red]")
                sys.exit(1)
        else:
            bonfire_id = console.input("  Bonfire ID: ").strip()

    # Pick agent
    if not agent_id:
        console.print()
        console.print("  [dim]Fetching agents...[/dim]", end=" ")
        headers["X-Bonfire-Id"] = bonfire_id
        try:
            resp = requests.get(f"{api_url}/agents", params={"bonfire_id": bonfire_id}, headers=headers, timeout=10)
            if resp.ok:
                console.print("[green]OK[/green]")
                agents_data = resp.json()
                agents_list = agents_data if isinstance(agents_data, list) else agents_data.get("agents", agents_data.get("data", []))

                if agents_list:
                    console.print()
                    table = Table(title="Agents", title_style="bold", show_lines=False, padding=(0, 2))
                    table.add_column("#", style="bold bright_blue", width=4)
                    table.add_column("Name", style="bold")
                    table.add_column("ID", style="dim")
                    table.add_column("Description", max_width=40)
                    for i, a in enumerate(agents_list, 1):
                        table.add_row(
                            str(i),
                            a.get("name", "—"),
                            a.get("_id", a.get("id", "—")),
                            truncate(a.get("description", ""), 40),
                        )
                    console.print(table)
                    console.print()

                    choice = console.input(f"  Select agent [dim](1-{len(agents_list)})[/dim]: ").strip()
                    try:
                        idx = int(choice) - 1
                        selected = agents_list[idx]
                        agent_id = selected.get("_id", selected.get("id"))
                        console.print(f"  [dim]Selected:[/dim] {selected.get('name', agent_id)}")
                    except (ValueError, IndexError):
                        console.print("[red]  Invalid selection.[/red]")
                        sys.exit(1)
                else:
                    agent_id = console.input("  Agent ID: ").strip()
            else:
                console.print("[yellow]Skipped[/yellow]")
                agent_id = console.input("  Agent ID: ").strip()
        except requests.RequestException:
            console.print("[yellow]Skipped[/yellow]")
            agent_id = console.input("  Agent ID: ").strip()

    if not agent_id:
        console.print("[red]  Agent ID is required.[/red]")
        sys.exit(1)

    # Write config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        f"BONFIRE_API_URL={api_url}\n"
        f"BONFIRE_ID={bonfire_id}\n"
        f"BONFIRE_AGENT_ID={agent_id}\n"
        f"BONFIRE_API_KEY={api_key}\n"
    )
    CONFIG_FILE.chmod(0o600)

    console.print()
    console.print(Panel.fit(
        f"[bold green]Configuration saved[/bold green]\n\n"
        f"  [dim]Config:[/dim] {CONFIG_FILE}\n"
        f"  [dim]API URL:[/dim] {api_url}\n"
        f"  [dim]Bonfire:[/dim] {bonfire_id}\n"
        f"  [dim]Agent:[/dim] {agent_id}\n\n"
        f"  Try it: [bold]bonfire chat \"hello\"[/bold]",
        border_style="green",
    ))


@cli.command()
@click.argument("message")
@click.option(
    "--graph-mode", "-g",
    default="regenerate",
    type=click.Choice(["regenerate", "append", "adaptive", "static"]),
    help="Graph interaction mode (default: regenerate).",
)
def chat(message, graph_mode):
    """Send a message to a Bonfire agent.

    By default, queries the knowledge graph and builds a fresh context graph
    for each message. Use --graph-mode to change this behavior.
    """
    cfg = get_config()
    body = {
        "message": message,
        "agent_id": cfg["agent_id"],
        "bonfire_id": cfg["bonfire_id"],
        "chat_history": [],
        "graph_mode": graph_mode,
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
@click.option("-f", "--file", "file_path", type=click.Path(exists=True), help="Ingest a .md file as a document.")
@click.option("--title", default=None, help="Title for the ingested document.")
def sync(message, file_path, title):
    """Push context to the Bonfires knowledge graph.

    The message is always pushed to the stack. Optionally pass -f to also
    ingest a markdown file as a document.
    """
    cfg = get_config()

    chat_id = _git_chat_id()
    repo = chat_id.split(":")[0] if ":" in chat_id else "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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

    console.print("[bold]2/2[/bold] Processing stack...", end=" ")
    api_post(cfg, f"/agents/{cfg['agent_id']}/stack/process", {})
    console.print("[green]OK[/green]")

    if file_path:
        if not file_path.endswith(".md"):
            console.print(f"[yellow]Warning:[/yellow] Only .md files supported for now, got {file_path}")
            return
        console.print(f"[bold]+[/bold] Ingesting [cyan]{file_path}[/cyan]...", end=" ")
        content = Path(file_path).read_text()
        doc_title = title or Path(file_path).stem.replace("-", " ").replace("_", " ").title()
        ingest_body = {
            "content": content,
            "title": doc_title,
            "bonfire_id": cfg["bonfire_id"],
            "agent_id": cfg["agent_id"],
            "metadata": {
                "type": "memory-sync",
                "source": "bonfire-cli",
                "repo": repo,
                "file": file_path,
            },
        }
        ingest_resp = api_post(cfg, "/ingest_content", ingest_body)
        doc_id = ingest_resp.get("document_id", "unknown")
        console.print(f"[green]OK[/green] (doc: [dim]{doc_id}[/dim])")

    console.print(Panel(
        f"[bold]Context synced[/bold]\n\n"
        f"  Chat ID: [cyan]{chat_id}[/cyan]\n"
        f"  Repo: [cyan]{repo}[/cyan]\n"
        f"  Message: {truncate(message, 80)}"
        + (f"\n  File: [cyan]{file_path}[/cyan]" if file_path else ""),
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


cli.add_command(kengram_group)


if __name__ == "__main__":
    cli()
