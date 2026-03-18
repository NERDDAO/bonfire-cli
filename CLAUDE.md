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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **bonfire-cli** (401 symbols, 1329 relationships, 32 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/bonfire-cli/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/bonfire-cli/context` | Codebase overview, check index freshness |
| `gitnexus://repo/bonfire-cli/clusters` | All functional areas |
| `gitnexus://repo/bonfire-cli/processes` | All execution flows |
| `gitnexus://repo/bonfire-cli/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

- Re-index: `npx gitnexus analyze`
- Check freshness: `npx gitnexus status`
- Generate docs: `npx gitnexus wiki`

<!-- gitnexus:end -->
