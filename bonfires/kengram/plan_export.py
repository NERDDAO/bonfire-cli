"""Export a kEngram as a markdown implementation plan."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bonfires.kengram.manifest import KEngramManifest


def topological_sort(task_uuids: list[str], edges: list[dict[str, str]]) -> list[str]:
    """Sort tasks by DEPENDS_ON edges. Returns ordered UUIDs."""
    depends = [e for e in edges if e["name"] == "DEPENDS_ON"]
    # Build adjacency: if A DEPENDS_ON B, B must come before A
    in_degree: dict[str, int] = {u: 0 for u in task_uuids}
    graph: dict[str, list[str]] = {u: [] for u in task_uuids}
    for e in depends:
        src = e["source_node_uuid"]  # the task that depends
        tgt = e["target_node_uuid"]  # the prerequisite
        if src in in_degree and tgt in in_degree:
            graph[tgt].append(src)
            in_degree[src] += 1
    queue: deque[str] = deque(u for u in task_uuids if in_degree[u] == 0)
    result: list[str] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for child in graph[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    # Append any remaining (cycle members) at end
    for u in task_uuids:
        if u not in result:
            result.append(u)
    return result


def export_plan(
    manifest: KEngramManifest,
    entities: list[dict[str, object]],
    edges: list[dict[str, str]],
) -> str:
    """Generate markdown plan from a kEngram manifest."""
    # Separate entities by type
    goal: dict[str, object] | None = None
    tasks: list[dict[str, object]] = []
    code_targets: dict[str, dict[str, object]] = {}
    for e in entities:
        labels = e.get("labels", [])
        assert isinstance(labels, list)
        if "Goal" in labels and "Task" in labels:
            goal = e
        elif "Task" in labels:
            tasks.append(e)
        else:
            uuid = str(e["uuid"])
            code_targets[uuid] = e

    # Sort tasks
    task_uuids = [str(t["uuid"]) for t in tasks]
    sorted_uuids = topological_sort(task_uuids, edges)
    task_map = {str(t["uuid"]): t for t in tasks}
    sorted_tasks = [task_map[u] for u in sorted_uuids if u in task_map]

    # Build per-task file associations from edges
    task_files: dict[str, list[str]] = {}
    for e in edges:
        if e["name"] in ("MODIFIES", "CREATES", "TESTS"):
            src = e["source_node_uuid"]
            tgt = e["target_node_uuid"]
            target_entity = code_targets.get(tgt)
            if target_entity and src in task_map:
                target_name = str(target_entity["name"])
                task_files.setdefault(src, []).append(
                    f"{e['name'].lower()}: {target_name}"
                )

    # Render
    lines: list[str] = []
    name = manifest.name or manifest.id

    lines.append(f"# {name} Implementation Plan")
    lines.append("")
    lines.append(
        f"> **kEngram:** `{manifest.id}` | **Merkle:** `{manifest.merkle_root[:16]}...`"
    )
    lines.append(
        "> **For agentic workers:** Use superpowers:subagent-driven-development"
        " or superpowers:executing-plans"
    )
    lines.append("")

    if goal:
        lines.append(f"**Goal:** {goal.get('summary', '')}")
        lines.append("")

    lines.append("---")
    lines.append("")

    for i, task in enumerate(sorted_tasks, 1):
        task_name = str(task["name"]).removeprefix("Task: ")
        lines.append(f"### Task {i}: {task_name}")
        lines.append("")
        files = task_files.get(str(task["uuid"]), [])
        if files:
            lines.append("**Files:**")
            for f in files:
                lines.append(f"- {f}")
            lines.append("")
        summary = str(task.get("summary", ""))
        if summary:
            # Convert summary steps to checkboxes
            for line in summary.split("\n"):
                stripped = line.strip()
                if stripped.lower().startswith("step "):
                    lines.append(f"- [ ] **{stripped}**")
                else:
                    lines.append(line)
            lines.append("")

    return "\n".join(lines)
