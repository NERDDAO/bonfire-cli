"""Bonfire CLI — Beautiful terminal interface for the Bonfires API."""

import json
import subprocess
import sys
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bonfires import __version__
from bonfires.config import CONFIG_DIR, CONFIG_FILE, DEFAULT_API_URL
from bonfires.formatting import (
    format_chat_response,
    format_delve_response,
    format_episodes,
    format_graph,
    truncate,
)
from bonfires.kengram.commands import kengram as kengram_group
from bonfires.sdk import BonfiresClient
from bonfires.sdk.exceptions import APIError, ConfigError

console = Console()


def _get_client() -> BonfiresClient:
    """Build a BonfiresClient from env config. Prints error + exits on failure."""
    try:
        return BonfiresClient()
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Run [bold]bonfire init[/bold] to set up your configuration.")
        sys.exit(1)


def _handle_api_error(e: APIError) -> None:
    """Print API error and exit."""
    console.print(
        Panel(
            e.response_text[:500],
            title=f"API Error {e.status_code}",
            border_style="red",
        )
    )
    sys.exit(1)


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
@click.option(
    "--bonfire-id", default=None, help="Bonfire ID (skip interactive prompt)."
)
@click.option("--agent-id", default=None, help="Agent ID (skip interactive prompt).")
def init(api_url, api_key, bonfire_id, agent_id):
    """Set up Bonfires CLI configuration.

    Walks you through connecting to the Bonfires API and saves your
    credentials to ~/.config/bonfires/config.env.
    """
    console.print()
    console.print(
        Panel.fit(
            "[bold bright_blue]Bonfires CLI[/bold bright_blue]\n"
            "[dim]Terminal interface for the Bonfires AI knowledge graph[/dim]",
            border_style="bright_blue",
        )
    )
    console.print()

    # API URL
    if not api_url:
        api_url = (
            console.input(f"  API URL [dim]({DEFAULT_API_URL})[/dim]: ").strip()
            or DEFAULT_API_URL
        )
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
        console.print("[red]Failed[/red]")
        console.print(f"  [red]{e}[/red]")
        sys.exit(1)

    # Pick bonfire
    if not bonfire_id:
        bonfires_data = resp.json()
        bonfires_list = (
            bonfires_data
            if isinstance(bonfires_data, list)
            else bonfires_data.get("bonfires", bonfires_data.get("data", []))
        )

        if bonfires_list:
            console.print()
            table = Table(
                title="Your Bonfires",
                title_style="bold",
                show_lines=False,
                padding=(0, 2),
            )
            table.add_column("#", style="bold bright_blue", width=4)
            table.add_column("Name", style="bold")
            table.add_column("ID", style="dim")
            for i, b in enumerate(bonfires_list, 1):
                table.add_row(
                    str(i), b.get("name", "—"), b.get("_id", b.get("id", "—"))
                )
            console.print(table)
            console.print()

            choice = console.input(
                f"  Select bonfire [dim](1-{len(bonfires_list)})[/dim]: "
            ).strip()
            try:
                idx = int(choice) - 1
                selected = bonfires_list[idx]
                bonfire_id = selected.get("_id", selected.get("id"))
                console.print(
                    f"  [dim]Selected:[/dim] {selected.get('name', bonfire_id)}"
                )
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
            resp = requests.get(
                f"{api_url}/agents",
                params={"bonfire_id": bonfire_id},
                headers=headers,
                timeout=10,
            )
            if resp.ok:
                console.print("[green]OK[/green]")
                agents_data = resp.json()
                agents_list = (
                    agents_data
                    if isinstance(agents_data, list)
                    else agents_data.get("agents", agents_data.get("data", []))
                )

                if agents_list:
                    console.print()
                    table = Table(
                        title="Agents",
                        title_style="bold",
                        show_lines=False,
                        padding=(0, 2),
                    )
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

                    choice = console.input(
                        f"  Select agent [dim](1-{len(agents_list)})[/dim]: "
                    ).strip()
                    try:
                        idx = int(choice) - 1
                        selected = agents_list[idx]
                        agent_id = selected.get("_id", selected.get("id"))
                        console.print(
                            f"  [dim]Selected:[/dim] {selected.get('name', agent_id)}"
                        )
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
    console.print(
        Panel.fit(
            f"[bold green]Configuration saved[/bold green]\n\n"
            f"  [dim]Config:[/dim] {CONFIG_FILE}\n"
            f"  [dim]API URL:[/dim] {api_url}\n"
            f"  [dim]Bonfire:[/dim] {bonfire_id}\n"
            f"  [dim]Agent:[/dim] {agent_id}\n\n"
            f'  Try it: [bold]bonfire chat "hello"[/bold]',
            border_style="green",
        )
    )

    # Sync Claude Code skills from repo to ~/.claude/skills/
    _sync_skills()


@cli.command()
@click.argument("message")
@click.option(
    "--graph-mode",
    "-g",
    default="regenerate",
    type=click.Choice(["regenerate", "append", "adaptive", "static"]),
    help="Graph interaction mode (default: regenerate).",
)
def chat(message, graph_mode):
    """Send a message to a Bonfire agent.

    By default, queries the knowledge graph and builds a fresh context graph
    for each message. Use --graph-mode to change this behavior.
    """
    client = _get_client()
    try:
        data = client.agents.chat(message, graph_mode=graph_mode)
    except APIError as e:
        _handle_api_error(e)
    format_chat_response(data)


@cli.command()
@click.argument("query")
@click.option("-n", "--num-results", default=10, help="Number of results to return.")
def delve(query, num_results):
    """Search the Bonfires knowledge graph."""
    client = _get_client()
    try:
        data = client.kg.search(query, num_results=num_results)
    except APIError as e:
        _handle_api_error(e)
    format_delve_response(data, query)


@cli.group()
def episodes():
    """Browse and inspect episodes."""
    pass


@episodes.command(name="latest")
@click.option("-n", "--num", default=5, help="Number of episodes to return.")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def episodes_latest(num, output_json):
    """Show the most recent episodes."""
    client = _get_client()
    try:
        eps = client.kg.get_latest_episodes(limit=num)
    except APIError as e:
        _handle_api_error(e)
    if output_json:
        import json as _json

        console.print(_json.dumps(eps, indent=2, default=str))
        return
    if not eps:
        console.print("[dim]No episodes found.[/dim]")
        return
    format_episodes(eps)


@episodes.command(name="show")
@click.argument("uuid")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def episodes_show(uuid, output_json):
    """Show a single episode by UUID."""
    client = _get_client()
    try:
        from bonfires.sdk.http import _get

        result = _get(
            client._config,
            f"/knowledge_graph/episode/{uuid}",
            params={"bonfire_id": client._config.bonfire_id},
        )
    except APIError as e:
        _handle_api_error(e)
    if output_json:
        import json as _json

        console.print(_json.dumps(result, indent=2, default=str))
        return
    if isinstance(result, dict):
        ep = result.get("episode", result)
        console.print(Panel(
            f"[bold]{ep.get('name', '—')}[/bold]\n\n"
            f"{ep.get('content', {}).get('content', '') if isinstance(ep.get('content'), dict) else ''}\n\n"
            f"[dim]UUID: {ep.get('uuid', '—')}[/dim]\n"
            f"[dim]Date: {(ep.get('valid_at') or ep.get('created_at', ''))[:19]}[/dim]",
            title="Episode",
        ))


@cli.group(name="agents", invoke_without_command=True)
@click.pass_context
def agents_group(ctx):
    """Manage agents — list, create, show, update, delete."""
    if ctx.invoked_subcommand is None:
        # Default: list agents (backwards compat with old `bonfire agents`)
        client = _get_client()
        try:
            agents_list = client.agents.list()
        except APIError as e:
            _handle_api_error(e)
        table = Table(title="Agents", title_style="bold green")
        table.add_column("Name", style="bold")
        table.add_column("ID", style="dim")
        table.add_column("Platform", style="cyan")
        table.add_column("Active", style="green")
        for a in agents_list:
            table.add_row(
                a.get("name", "—"),
                a.get("_id", a.get("id", "—")),
                a.get("deploymentConfiguration", {}).get("platform", "—"),
                "✓" if a.get("is_active") or a.get("isActive") else "✗",
            )
        console.print(table)


@agents_group.command(name="create")
@click.argument("name")
@click.argument("username")
@click.option("--context", "-c", required=True, help="System prompt / personality.")
@click.option("--platform", default="matrix", help="Platform: matrix, telegram, discord.")
@click.option("--tools", "-t", multiple=True, help="MCP tool provider IDs to enable.")
@click.option("--env", "-e", multiple=True, help="Env vars as KEY=VALUE pairs.")
@click.option("--matrix-homeserver", default="", help="Matrix homeserver URL.")
@click.option("--matrix-as-token", default="", help="Matrix appservice token.")
@click.option("--matrix-hs-token", default="", help="Matrix homeserver token.")
@click.option("--inactive", is_flag=True, help="Create as inactive (don't start immediately).")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def agents_create(name, username, context, platform, tools, env, matrix_homeserver,
                  matrix_as_token, matrix_hs_token, inactive, output_json):
    """Create a new agent on the configured bonfire."""
    client = _get_client()

    # Parse env vars
    env_vars = {}
    for e in env:
        if "=" in e:
            k, v = e.split("=", 1)
            env_vars[k] = v

    # Build deployment config
    deploy_config: dict = {}
    if matrix_homeserver:
        deploy_config["matrixHomeserverUrl"] = matrix_homeserver
    if matrix_as_token:
        deploy_config["matrixAsToken"] = matrix_as_token
    if matrix_hs_token:
        deploy_config["matrixHsToken"] = matrix_hs_token

    try:
        result = client.agents.create(
            name=name,
            username=username,
            context=context,
            platform=platform,
            is_active=not inactive,
            deployment_config=deploy_config or None,
            enabled_mcp_tools=list(tools) if tools else None,
            agent_env_vars=env_vars or None,
        )
    except APIError as e:
        _handle_api_error(e)

    if output_json:
        import json as _json
        console.print(_json.dumps(result, indent=2, default=str))
        return

    agent_id = result.get("_id", result.get("id", "—"))
    console.print(Panel(
        f"[bold]{name}[/bold] (@{username})\n\n"
        f"[dim]ID: {agent_id}[/dim]\n"
        f"Platform: {platform}\n"
        f"Active: {'yes' if not inactive else 'no'}\n"
        f"Tools: {', '.join(tools) if tools else 'none'}",
        title="[green]Agent Created[/green]",
    ))


@agents_group.command(name="show")
@click.argument("agent_id")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def agents_show(agent_id, output_json):
    """Show details for a specific agent."""
    client = _get_client()
    try:
        data = client.agents.get(agent_id)
    except APIError as e:
        _handle_api_error(e)

    if output_json:
        import json as _json
        console.print(_json.dumps(data, indent=2, default=str))
        return

    agent = data.get("agent", data) if isinstance(data, dict) else data
    deploy = agent.get("deploymentConfiguration", {})
    features = agent.get("agentFeatures", {})
    tools_list = agent.get("enabledMcpTools", [])

    console.print(Panel(
        f"[bold]{agent.get('name', '—')}[/bold] (@{agent.get('username', '—')})\n\n"
        f"[dim]ID: {agent.get('_id', agent.get('id', '—'))}[/dim]\n"
        f"Platform: {deploy.get('platform', '—')}\n"
        f"Active: {'yes' if agent.get('is_active') or agent.get('isActive') else 'no'}\n"
        f"Tools: {', '.join(tools_list) if tools_list else 'none'}\n\n"
        f"[dim]Context:[/dim]\n{truncate(agent.get('context', ''), 300)}",
        title="Agent Details",
    ))


@agents_group.command(name="delete")
@click.argument("agent_id")
@click.confirmation_option(prompt="Are you sure you want to delete this agent?")
def agents_delete(agent_id):
    """Delete an agent."""
    client = _get_client()
    try:
        client.agents.delete(agent_id)
    except APIError as e:
        _handle_api_error(e)
    console.print(f"[green]Deleted agent {agent_id}[/green]")


@cli.command(name="bonfires")
def list_bonfires():
    """List all bonfires."""
    client = _get_client()
    try:
        bonfires_list = client.agents.list_bonfires()
    except APIError as e:
        _handle_api_error(e)
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
@click.option(
    "-f",
    "--file",
    "file_path",
    type=click.Path(exists=True),
    help="Ingest a .md file as a document.",
)
@click.option("--title", default=None, help="Title for the ingested document.")
def sync(message, file_path, title):
    """Push context to the Bonfires knowledge graph.

    The message is always pushed to the stack. Optionally pass -f to also
    ingest a markdown file as a document.
    """
    client = _get_client()
    chat_id = _git_chat_id()

    if file_path and not file_path.endswith(".md"):
        console.print(
            f"[yellow]Warning:[/yellow] Only .md files supported for now, got {file_path}"
        )
        return

    try:
        console.print("[bold]1/2[/bold] Pushing to stack...", end=" ")
        result = client.agents.sync(
            message, chat_id=chat_id, file_path=file_path, title=title
        )
        console.print("[green]OK[/green]")

        console.print("[bold]2/2[/bold] Processing stack...", end=" ")
        console.print("[green]OK[/green]")

        if file_path:
            doc_id = result.get("document_id", "unknown")
            console.print(
                f"[bold]+[/bold] Ingested [cyan]{file_path}[/cyan] "
                f"(doc: [dim]{doc_id}[/dim])"
            )
    except APIError as e:
        console.print("[red]FAILED[/red]")
        _handle_api_error(e)

    repo = chat_id.split(":")[0] if ":" in chat_id else "unknown"
    console.print(
        Panel(
            f"[bold]Context synced[/bold]\n\n"
            f"  Chat ID: [cyan]{chat_id}[/cyan]\n"
            f"  Repo: [cyan]{repo}[/cyan]\n"
            f"  Message: {truncate(message, 80)}"
            + (f"\n  File: [cyan]{file_path}[/cyan]" if file_path else ""),
            title="Sync Complete",
            border_style="green",
        )
    )


def _sync_skills() -> None:
    """Sync Claude Code skills from the repo's .claude/skills/ to ~/.claude/skills/."""
    import hashlib
    import shutil

    repo_root = Path(__file__).resolve().parent.parent
    source_dir = repo_root / ".claude" / "skills"
    target_dir = Path.home() / ".claude" / "skills"

    if not source_dir.exists():
        return

    skill_files = list(source_dir.rglob("*/SKILL.md"))
    if not skill_files:
        return

    console.print()
    console.print("[bold]Syncing Claude Code skills...[/bold]")
    for skill_file in sorted(skill_files):
        skill_name = skill_file.parent.name
        target_path = target_dir / skill_name / "SKILL.md"

        src_hash = hashlib.sha256(skill_file.read_bytes()).hexdigest()
        if target_path.exists():
            tgt_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
            if src_hash == tgt_hash:
                console.print(f"  [dim]OK[/dim]      {skill_name}")
                continue

        action = "Updated" if target_path.exists() else "Created"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_file, target_path)
        console.print(f"  [green]{action}[/green]  {skill_name}")

    console.print("[dim]  Skills ready.[/dim]")


def _git_chat_id():
    """Derive a chatId from git repo name + branch."""
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        repo = (
            Path(toplevel.stdout.strip()).name
            if toplevel.returncode == 0
            else "unknown"
        )
        br = branch.stdout.strip() if branch.returncode == 0 else "unknown"
        return f"{repo}:{br}"
    except Exception:
        return "bonfire-cli:unknown"


cli.add_command(kengram_group)


if __name__ == "__main__":
    cli()
