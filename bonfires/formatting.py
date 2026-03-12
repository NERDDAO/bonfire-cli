"""Rich formatting for Bonfires API responses."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()

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
    entity_map = {}
    if entities:
        for ent in entities:
            entity_map[ent.get("uuid", "")] = ent.get("name", ent.get("uuid", "?"))

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
    """Render all graph data found in a response."""
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

    action = data.get("graph_action", "")
    if action:
        color = ACTION_COLORS.get(action, "red")
        console.print(f"  Graph Action: [{color}]{action}[/{color}]")

    errors = data.get("errors", [])
    if errors:
        for err in errors:
            console.print(f"  [red]Error: {err}[/red]")

    graph_data = data.get("graph_data")
    if graph_data:
        console.print()
        format_graph(graph_data)


def format_delve_response(data, query=""):
    """Render a delve API response."""
    num = data.get("num_results", 0)
    console.print(f'\n[bold]Delve:[/bold] "{query}" — [cyan]{num} results[/cyan]\n')
    format_graph(data)

    metrics = data.get("metrics", {})
    duration = metrics.get("duration_ms")
    if duration:
        console.print(f"\n[dim]Search completed in {duration:.0f}ms[/dim]")
