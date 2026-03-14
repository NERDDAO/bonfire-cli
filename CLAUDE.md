# Bonfires CLI

A Click-based CLI for the Bonfires AI API. Package structure under `bonfires/`.

## Architecture

```
bonfires/
  __init__.py    # version
  cli.py         # Click commands (init, chat, delve, sync, agents, etc.)
  config.py      # Config loading: env vars > .env > ~/.config/bonfires/config.env
  api.py         # API client (api_post, api_get)
  formatting.py  # Rich formatters for chat, delve, graph responses
  kengram/
    __init__.py    # package init
    manifest.py    # KEngramManifest dataclass + JSON I/O
    hashing.py     # SHA-256 content hashing + merkle tree
    storage.py     # Vault directory read/write/active tracking
    canvas.py      # Export to Obsidian .canvas format
    commands.py    # Click command group: new, pin, show, merge, export, verify
```

## Config Priority

1. Environment variables (highest)
2. `.env` in current directory
3. `~/.config/bonfires/config.env` (created by `bonfire init`)

## API Contract

The chat endpoint accepts `graph_mode` with these values:

| Value | Behavior |
|-------|----------|
| `adaptive` | LLM decides dynamically whether to query the knowledge graph |
| `static` | No graph query, no graph changes |
| `regenerate` | Always queries KG, creates fresh graph from scratch |
| `append` | Always queries KG, adds to existing graph |

`"dynamic"` is accepted as an alias for `"adaptive"` by the API.

**Do NOT use** `search`, `fetch`, `expand`, or `do_nothing` as `graph_mode` values — those are *response* graph actions, not valid request parameters.

## Running

```bash
pip install -e .
bonfire init
bonfire chat "hello"
```

## kEngrams

Verifiable knowledge subgraphs — curated projections of the canonical Bonfires KG.

```bash
bonfire kengram new "Session Name"     # create and set active
bonfire kengram pin <uuid> --name X    # pin a KG entity
bonfire kengram show                   # show active kEngram
bonfire kengram verify                 # check merkle root integrity
bonfire kengram merge <src> --into <tgt>  # merge session → topic
bonfire kengram export                 # export to .canvas
bonfire kengram list                   # list all
```

Config: set `BONFIRE_VAULT_DIR` to control where manifests/canvas files are stored (default: `~/Vaults/Bonfires/vault`).

## Testing

No test suite yet. Verify changes manually:

```bash
bonfire --version
bonfire init --help
bonfire chat "test message"
bonfire delve "test query"
bonfire agents
```
