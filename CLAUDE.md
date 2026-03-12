# Bonfire CLI

A Click-based CLI for the Bonfires AI API. Single-file app in `bonfire.py`.

## Architecture

- **Config**: loaded from `.env` via `python-dotenv`
- **API client**: `api_post` / `api_get` with auth headers from config
- **Formatters**: Rich-based renderers for chat responses, delve results, graph data
- **Commands**: `chat`, `delve`, `sync`, `agents`, `bonfires`, `graph`, `format-chat`, `format-delve`

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
bonfire chat "hello"
```

## Testing

No test suite yet. Verify changes manually:

```bash
bonfire chat "test message"
bonfire delve "test query"
bonfire agents
```
