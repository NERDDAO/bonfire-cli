# Bonfires

SDK and CLI for the [Bonfires AI](https://bonfires.ai) API. Chat with agents, search the knowledge graph, manage kEngrams, and sync context — from Python code or the command line.

## Install

```bash
pip install bonfires
```

Or install from source:

```bash
pip install git+https://github.com/NERDDAO/bonfire-cli.git
```

## SDK

Use the Bonfires API programmatically from any Python code — AI agents, scripts, backend services.

```python
from bonfires import BonfiresClient

client = BonfiresClient(
    api_key="...",
    bonfire_id="...",
    agent_id="...",
    vault_dir="/path/to/vault",
)
# Or load everything from env vars / dotenv:
client = BonfiresClient()
```

### Knowledge Graph

```python
results = client.kg.search("authentication patterns", num_results=10)
entity = client.kg.get_entity("uuid-here")
uuid = client.kg.create_entity("Auth Service", labels=["Service"], attributes={"summary": "Handles auth"})
client.kg.create_edge(source_uuid, target_uuid, name="DEPENDS_ON", fact="Auth required")
```

### Agents

```python
response = client.agents.chat("What do we know about auth?", graph_mode="regenerate")
client.agents.sync("Shipped v2 of the auth service", chat_id="myrepo:main")
agents = client.agents.list()
```

### kEngrams

```python
manifest = client.kengrams.create("Sprint Review", type="session")
result = client.kengrams.pin(manifest.id, "entity-uuid")
client.kengrams.add_edge(manifest.id, src, tgt, "RELATES_TO", sync_to_kg=True)
client.kengrams.batch(manifest.id, {"nodes": [...], "edges": [...]}, sync_to_kg=True)
verification = client.kengrams.verify(manifest.id)
path = client.kengrams.export(manifest.id, format="canvas")
client.kengrams.push(manifest.id)  # push local-only entities to canonical KG
```

### Ontology Profiles

```python
prof = client.ontology.create_profile("My Ontology", namespaces={"foaf": "http://xmlns.com/foaf/0.1/"})
client.ontology.attach_profile(kengram_id, prof.id)
gaps = client.ontology.extract_gaps(kengram_id)
```

### Error Handling

```python
from bonfires import BonfiresClient, APIError, NotFoundError, ConfigError

try:
    client = BonfiresClient()
    entity = client.kg.get_entity("missing-uuid")
except ConfigError as e:
    print(f"Config problem: {e}")
except NotFoundError as e:
    print(f"Not found: {e}")
except APIError as e:
    print(f"API error {e.status_code}: {e.response_text}")
```

## CLI

### Getting Started

```bash
bonfire init          # interactive setup wizard
bonfire chat "hello"  # send a message to your agent
```

`bonfire init` connects to the API, lists your bonfires and agents, and saves credentials to `~/.config/bonfires/config.env`.

### Commands

**Chat & Search**

```bash
bonfire chat "What do we know about auth patterns?"
bonfire chat --graph-mode adaptive "let the agent decide"
bonfire delve "error handling patterns"
bonfire delve -n 20 "authentication architecture"
```

**Sync Context**

```bash
bonfire sync "shipped bonfire-cli v0.4"
bonfire sync "design spec for auth" -f docs/auth-design.md
```

**List Resources**

```bash
bonfire agents     # list agents
bonfire bonfires   # list bonfires
```

**Render & Format**

```bash
bonfire graph results.json
cat graph.json | bonfire graph
curl -s ... | bonfire format-chat
```

**kEngram Management**

```bash
bonfire kengram new "Session Name"             # create and set active
bonfire kengram pin <uuid>                     # pin entity (auto-fetches from KG)
bonfire kengram pin --search "rubric pipeline" # search KG, pick from results
bonfire kengram create "Entity" --summary "..."# push new entity to KG + pin
bonfire kengram edge <src> <tgt> --name USES   # add edge (syncs to KG)
bonfire kengram edge <src> <tgt> --name X --local  # local-only edge
bonfire kengram batch changeset.json --sync    # bulk apply nodes + edges
bonfire kengram verify                         # check against canonical KG
bonfire kengram verify --local                 # local-only integrity check
bonfire kengram push                           # push local entities to KG
bonfire kengram repin <uuid>                   # re-fetch and update hash
bonfire kengram export                         # export to Obsidian .canvas
bonfire kengram export --format plan           # export as markdown plan
bonfire kengram export --format owl            # export as OWL/RDF
bonfire kengram merge <src> --into <tgt>       # merge session -> topic
bonfire kengram show                           # show active kEngram
bonfire kengram list                           # list all
bonfire kengram delete <id> --force            # remove a kEngram
```

All kengram commands support `--json` for machine-readable output.

**Ontology Profiles**

```bash
bonfire kengram profile new "My Ontology"
bonfire kengram profile attach <profile-id>
bonfire kengram profile validate
bonfire kengram profile suggest
bonfire kengram profile gaps
bonfire kengram profile match --ontology <id>
```

### JSON Mode

Every kengram and profile command supports `--json` for structured output:

```bash
bonfire kengram new "Test" --json
# {"status": "created", "id": "ke-2026-03-28-test", "name": "Test", ...}

bonfire kengram verify --json
# {"status": "verified", "merkle_root": "abc123...", "nodes": {...}, ...}
```

## Configuration

Config is loaded in this order (later overrides earlier):

1. `~/.config/bonfires/config.env` (created by `bonfire init`)
2. `.env` in the current directory
3. Environment variables
4. Explicit parameters passed to `BonfiresClient()`

| Variable | Description |
|----------|-------------|
| `BONFIRE_API_URL` | API base URL (default: `https://tnt-v2.api.bonfires.ai`) |
| `BONFIRE_ID` | Your bonfire ID |
| `BONFIRE_AGENT_ID` | Agent ID to interact with |
| `BONFIRE_API_KEY` | API key for authentication |
| `BONFIRE_VAULT_DIR` | kEngram storage directory (default: `~/Vaults/Bonfires/vault`) |
