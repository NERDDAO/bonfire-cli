# Bonfire CLI

A terminal interface for the [Bonfires AI](https://bonfires.ai) API. Chat with agents, search the knowledge graph, sync context, and render graph data — all from the command line.

## Install

```bash
git clone https://github.com/NERDDAO/bonfire-cli.git
cd bonfire-cli
./install.sh
```

This creates an isolated Python venv and installs a `bonfire` command in `~/.local/bin`. Works from any directory — no need to activate a venv.

To update after pulling new changes, just re-run `./install.sh`.

## Setup

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `BONFIRE_API_URL` | API base URL (default: `https://tnt-v2.api.bonfires.ai`) |
| `BONFIRE_ID` | Your bonfire ID |
| `BONFIRE_AGENT_ID` | Agent ID to interact with |
| `BONFIRE_API_KEY` | API key for authentication |

## Commands

### `bonfire chat`

Send a message to a Bonfire agent. Searches the knowledge graph by default.

```bash
bonfire chat "What do we know about auth patterns?"
```

Use `--graph-mode` to control graph behavior:

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

```bash
bonfire agents
```

### `bonfire bonfires`

List all bonfires.

```bash
bonfire bonfires
```

### `bonfire graph`

Render graph data from a JSON file or stdin.

```bash
cat graph.json | bonfire graph
bonfire graph results.json
```

### `bonfire format-chat` / `bonfire format-delve`

Format raw API responses piped from stdin — useful for scripting with `curl`.

```bash
curl -s ... | bonfire format-chat
curl -s ... | bonfire format-delve -q "original query"
```

## Claude Code Integration

Bonfire CLI is used by three Claude Code skills:

- **bonfires-query** — `bonfire chat` for agent conversations
- **bonfires-delve** — `bonfire delve` for knowledge graph search
- **bonfires-sync** — `bonfire sync` for pushing context

These skills auto-trigger during planning, brainstorming, and context sync operations.
