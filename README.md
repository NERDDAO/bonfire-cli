# Bonfires CLI

Terminal interface for the [Bonfires AI](https://bonfires.ai) API. Chat with agents, search the knowledge graph, sync context, and render graph data — all from the command line.

## Install

```bash
pip install bonfires
```

Or install from source:

```bash
pip install git+https://github.com/NERDDAO/bonfire-cli.git
```

For global install without polluting your Python environment:

```bash
pipx install bonfires
```

## Getting Started

Run the interactive setup:

```bash
bonfire init
```

This will:
1. Connect to the Bonfires API
2. List your bonfires and let you pick one
3. List available agents and let you pick one
4. Save credentials to `~/.config/bonfires/config.env`

You're ready to go:

```bash
bonfire chat "hello"
```

## Commands

### `bonfire init`

Interactive setup wizard. Connects to the API, lists your bonfires and agents, and saves config.

```bash
bonfire init
```

Or skip the prompts:

```bash
bonfire init --api-key YOUR_KEY --bonfire-id ID --agent-id ID
```

### `bonfire chat`

Send a message to a Bonfire agent. Searches the knowledge graph by default.

```bash
bonfire chat "What do we know about auth patterns?"
```

Control graph behavior with `--graph-mode`:

```bash
bonfire chat "find related context"                        # default: regenerate
bonfire chat --graph-mode adaptive "let the agent decide"
bonfire chat --graph-mode append "add to existing graph"
bonfire chat --graph-mode static "just reply, no graph"
```

### `bonfire delve`

Search the knowledge graph directly.

```bash
bonfire delve "error handling patterns"
bonfire delve -n 20 "authentication architecture"
```

### `bonfire sync`

Push context to the knowledge graph. Derives a chat ID from your current git repo and branch.

```bash
bonfire sync "shipped bonfire-cli v0.1"
bonfire sync "design spec for auth" -f docs/auth-design.md
```

### `bonfire agents`

List agents for the configured bonfire.

### `bonfire bonfires`

List all bonfires.

### `bonfire graph`

Render graph data from a JSON file or stdin.

```bash
bonfire graph results.json
cat graph.json | bonfire graph
```

### `bonfire format-chat` / `bonfire format-delve`

Format raw API responses piped from stdin — useful for scripting.

```bash
curl -s ... | bonfire format-chat
```

### `bonfire kengram`

Manage verifiable knowledge subgraphs — curated projections of the canonical Bonfires KG.

```bash
bonfire kengram new "Session Name"     # create and set active
bonfire kengram pin <uuid> --name X    # pin a KG entity
bonfire kengram show                   # show active kEngram
bonfire kengram verify                 # check merkle root integrity
bonfire kengram merge <src> --into <tgt>  # merge session → topic
bonfire kengram export                 # export to .canvas
bonfire kengram list                   # list all
```

Set `BONFIRE_VAULT_DIR` to control where manifests and canvas files are stored (default: `~/Vaults/Bonfires/vault`).

## Configuration

Config is loaded in this order (later overrides earlier):

1. `~/.config/bonfires/config.env` (created by `bonfire init`)
2. `.env` in the current directory
3. Environment variables

| Variable | Description |
|----------|-------------|
| `BONFIRE_API_URL` | API base URL (default: `https://tnt-v2.api.bonfires.ai`) |
| `BONFIRE_ID` | Your bonfire ID |
| `BONFIRE_AGENT_ID` | Agent ID to interact with |
| `BONFIRE_API_KEY` | API key for authentication |
