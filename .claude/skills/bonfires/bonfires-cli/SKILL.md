---
name: bonfires-cli
description: "Use when interacting with the Bonfires CLI — kEngram management, KG queries, context sync, agent chat. Covers all `bonfire` commands. NEVER edit kEngram manifest JSON directly."
---

# Bonfires CLI

Terminal interface for the Bonfires AI knowledge graph. Installed as `bonfire`.

## Top-Level Commands

| Command | Purpose |
|---------|---------|
| `bonfire init` | Configure API URL, key, bonfire ID, and agent ID |
| `bonfire chat "message"` | Chat with a Bonfire agent (queries KG for context) |
| `bonfire delve "query"` | Search the knowledge graph |
| `bonfire sync "message"` | Push context to the KG stack (optionally ingest a .md file with `-f`) |
| `bonfire agents` | List agents for the configured bonfire |
| `bonfire bonfires` | List all bonfires |
| `bonfire graph [file]` | Render graph data from JSON file or stdin |

## kEngram Commands

kEngrams are verifiable knowledge subgraphs — curated projections of the KG with content-addressed hashing (SHA-256) and merkle roots for integrity proof.

### Lifecycle

| Command | Purpose |
|---------|---------|
| `bonfire kengram new "name" [--type session\|topic]` | Create a new kEngram and set as active |
| `bonfire kengram use <id>` | Switch active kEngram |
| `bonfire kengram show [id]` | Display kEngram details (nodes, edges, merkle) |
| `bonfire kengram list` | List all kEngrams with status |
| `bonfire kengram delete <id> [--force]` | Delete a kEngram |

### Adding Content

| Command | Purpose |
|---------|---------|
| `bonfire kengram pin <uuid> [--to id]` | Pin a KG entity (fetches metadata from API) |
| `bonfire kengram pin <uuid> --name "X" --summary "Y" --labels "A,B"` | Pin with manual metadata (offline) |
| `bonfire kengram create "name" [--labels X] [--summary Y]` | Create entity in KG and pin it |
| `bonfire kengram edge <src> <tgt> --name REL [--fact "..."] [--local]` | Add edge between pinned nodes (`--local` skips KG sync) |
| `bonfire kengram unpin <uuid>` | Remove a node |
| `bonfire kengram repin <uuid>` | Re-fetch from KG and update hash |
| `bonfire kengram summary "text"` | Update the kEngram's summary |

### Batch Operations

**NEVER edit kEngram manifest JSON or canvas files directly. Use batch.**

```bash
bonfire kengram batch [--to <id>] [--canvas] [--sync] [--json] [FILE | -]
```

Accepts a changeset JSON:

```json
{
  "nodes": [
    { "uuid": "auto", "name": "My Entity", "summary": "Description", "labels": ["Entity"] }
  ],
  "edges": [
    { "source": "My Entity", "target": "Existing Node", "name": "DEPENDS_ON", "fact": "reason" }
  ]
}
```

**Key features:**
- `uuid: "auto"` generates a UUID4
- Edge `source`/`target` resolve by name: checks changeset nodes first, then existing manifest nodes, then treats as raw UUID if it contains `-`
- Single merkle recompute for all operations (batch mode)
- `--canvas` regenerates the Obsidian canvas
- `--sync` pushes edges to canonical KG
- `--json` returns machine-readable output with generated UUIDs

**Workflow:**
1. Write changeset to a temp file
2. `bonfire kengram batch --to <id> --canvas /tmp/changeset.json`
3. `bonfire kengram verify --local <id>`

### Verification & Export

| Command | Purpose |
|---------|---------|
| `bonfire kengram verify [id] [--local]` | Check merkle integrity (compares stored vs recomputed hashes). `--local` skips KG API. |
| `bonfire kengram export [id] --format canvas` | Export to Obsidian `.canvas` file |
| `bonfire kengram export [id] --format plan` | Export plan kEngram to markdown |
| `bonfire kengram merge <source> --into <target>` | Merge session into topic kEngram (idempotent) |

### kEngram Types

- **session**: Auto-dated (`ke-YYYY-MM-DD-slug`), created per work session
- **topic**: Named (`ke-topic-slug`), long-lived accumulation target for merges

### All Commands Support `--json`

Every kEngram command accepts `--json` for machine-readable output. Errors return `{"error": "message"}` with exit code 1.

## Common Patterns

### Add nodes + edges to an existing kEngram

```bash
cat > /tmp/changes.json << 'EOF'
{
  "nodes": [
    { "uuid": "auto", "name": "Feature X", "summary": "New capability", "labels": ["Task"] }
  ],
  "edges": [
    { "source": "Feature X", "target": "Goal Node", "name": "DECOMPOSES_INTO", "fact": "" }
  ]
}
EOF
bonfire kengram batch --to ke-topic-my-plan --canvas /tmp/changes.json
bonfire kengram verify --local ke-topic-my-plan
```

### Sync context after a conversation

```bash
bonfire sync "Summary of what was discussed and decided"
bonfire sync "Summary" -f docs/design.md --title "Design Document"
```

### Search KG and pin results interactively

```bash
bonfire kengram pin --search "authentication flow"
```
