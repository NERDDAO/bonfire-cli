# Bonfires SDK Design Spec (v2 — post-GAN review)

**Date:** 2026-03-27
**Status:** Final

## Context

The `bonfires` package (v0.3.0) is a CLI tool for interacting with the Bonfires AI API — KG search, agent chat, kEngram management, ontology operations. Business logic is coupled to CLI concerns (`sys.exit`, `console.print`, Click decorators), making it impossible to import programmatically. The goal is to extract a clean SDK layer (`bonfires.sdk`) so that AI agents, Python developers, and internal services can use the same operations without the CLI shell.

## Phased Delivery

The work is split into 4 PRs to isolate risk:

| PR | Scope | Risk | What breaks |
|----|-------|------|-------------|
| **PR 1** | SDK foundation + services (purely additive) | Low | Nothing — existing code untouched |
| **PR 2** | CLI refactoring to delegate to SDK | Medium | Test mock paths change |
| **PR 3** | Delete old modules (`api.py`, `kg_client.py`) | Low | Direct importers of deleted modules |
| **PR 4** | Version bump, re-exports, cleanup | Low | Nothing |

## Package Structure

```
bonfires/
├── __init__.py                    # re-exports BonfiresClient from sdk (PR 4)
├── sdk/
│   ├── __init__.py                # public API: BonfiresClient, exceptions, BonfiresConfig
│   ├── client.py                  # BonfiresClient — composes all services
│   ├── config.py                  # BonfiresConfig dataclass + from_env()
│   ├── http.py                    # _post(), _get() — raises APIError instead of sys.exit
│   ├── exceptions.py              # BonfiresError hierarchy
│   ├── kg.py                      # KGService — search, get/create/update entities, edges
│   ├── agents.py                  # AgentService — chat, sync, list agents/bonfires
│   ├── kengram.py                 # KEngramService — all kEngram operations
│   └── ontology.py                # OntologyService — profiles + ontology API ops
├── kengram/
│   ├── manifest.py                # KEngramManifest (unchanged)
│   ├── storage.py                 # KEngramStorage (unchanged)
│   ├── hashing.py                 # hash_node, hash_edge, merkle_root (unchanged)
│   ├── canvas.py                  # export_canvas (unchanged)
│   ├── plan_export.py             # export_plan (unchanged)
│   ├── ontology_pipeline.py       # RDF translation (unchanged)
│   ├── ontology_profile.py        # OntologyProfile model (unchanged)
│   ├── ontology_enrichment.py     # enrich_on_pin, validate_edge_pin (unchanged)
│   ├── commands.py                # REFACTORED in PR 2
│   ├── profile_commands.py        # REFACTORED in PR 2
│   └── kg_client.py               # DELETED in PR 3 (with deprecation shim)
├── cli.py                         # REFACTORED in PR 2
├── formatting.py                  # CLI-only (unchanged)
├── api.py                         # DELETED in PR 3 (with deprecation shim)
└── config.py                      # REFACTORED in PR 2
```

## Exception Hierarchy

```python
class BonfiresError(Exception):
    """Base exception for all SDK errors."""

class ConfigError(BonfiresError):
    """Missing or invalid configuration."""

class APIError(BonfiresError):
    """HTTP request failed."""
    def __init__(self, message: str, status_code: int, response_text: str):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class NotFoundError(BonfiresError):
    """Resource not found — local (kEngram/profile on disk) OR remote (404)."""
    def __init__(self, message: str, *, status_code: int = 0, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class StorageError(BonfiresError):
    """Local vault/filesystem operation failed."""

class AuthenticationError(APIError):
    """Authentication failed (401/403)."""
```

Key change from v1: `NotFoundError` extends `BonfiresError` (not `APIError`) since many "not found" situations are local (kEngram manifest missing, profile not on disk). `status_code` is optional, defaulting to 0 for local not-found.

## BonfiresConfig

```python
@dataclass
class BonfiresConfig:
    api_key: str
    bonfire_id: str
    agent_id: str
    api_url: str = "https://tnt-v2.api.bonfires.ai"
    vault_dir: str = ""  # MUST be provided or resolved from env
    group_id: str = ""   # computed: "{bonfire_id}:{agent_id}"

    def __post_init__(self):
        if not self.group_id:
            self.group_id = f"{self.bonfire_id}:{self.agent_id}"
        if not self.vault_dir:
            raise ConfigError("vault_dir must be configured (set BONFIRE_VAULT_DIR)")

    @classmethod
    def from_env(cls) -> BonfiresConfig:
        """Load from env vars + dotenv files.

        Priority: env vars > ~/.config/bonfires/config.env > .env
        Raises ConfigError if required keys missing.
        """
        ...
```

Key change from v1: `vault_dir` has no hardcoded default path. It must come from env vars or explicit configuration. `from_env()` reads `BONFIRE_VAULT_DIR` from the env/dotenv chain (the existing default `~/Vaults/Bonfires/vault` stays in the env-loading logic, not baked into the dataclass).

## BonfiresClient

```python
class BonfiresClient:
    kg: KGService
    agents: AgentService
    kengrams: KEngramService
    ontology: OntologyService

    def __init__(self, *, config: BonfiresConfig | None = None, **kwargs):
        # If config provided, use it.
        # If not, build BonfiresConfig from kwargs + env fallback.
        # Do NOT accept both config and individual params.
        ...
```

Key change from v1: Constructor takes `config` OR `**kwargs`, not both simultaneously. If `config` is passed, kwargs are ignored. This eliminates the precedence ambiguity.

## KGService

```python
class KGService:
    def search(self, query: str, num_results: int = 10) -> dict:
        """Search the KG via /delve. Returns FULL response dict (not just entities list).
        Callers extract what they need: result["entities"], result.get("query"), etc.
        """

    def get_entity(self, uuid: str) -> dict:
        """Fetch entity by UUID. Raises NotFoundError if missing."""

    def get_entities_batch(self, uuids: list[str]) -> list[dict]:
        """Fetch multiple entities. Raises APIError on failure."""

    def create_entity(self, name: str, labels: list[str], attributes: dict) -> str:
        """Create entity, return UUID."""

    def update_entity(self, uuid: str, name: str, labels: list[str], summary: str) -> dict:
        """Update entity metadata."""

    def create_edge(self, source_uuid: str, target_uuid: str, name: str, fact: str = "") -> dict:
        """Create edge between two entities."""
```

Key change from v1: `search()` returns the full response dict, not just the entity list. This preserves the data shape that `format_delve_response()` needs.

## AgentService

```python
class AgentService:
    def chat(self, message: str, graph_mode: str = "regenerate") -> dict:
        """Send message to bonfire agent. Returns full response dict."""

    def sync(
        self, message: str, *,
        chat_id: str = "",
        file_path: str | None = None,
        title: str | None = None,
    ) -> dict:
        """Push context to KG stack. Optionally ingest a markdown file.

        chat_id: identifier for the conversation (e.g. "repo:branch").
        If empty, defaults to "sdk:unknown".
        """

    def list(self) -> list[dict]:
        """List agents for the configured bonfire."""

    def list_bonfires(self) -> list[dict]:
        """List all bonfires."""
```

Key change from v1: `sync()` takes an explicit `chat_id` parameter. The `_git_chat_id()` helper stays in the CLI layer — it calls git subprocess and passes the result to `client.agents.sync(message, chat_id=_git_chat_id())`.

## KEngramService

```python
class KEngramService:
    def __init__(self, config: BonfiresConfig, http, kg: KGService):
        """KEngramService needs KGService for operations that touch the KG
        (pin with fetch, batch with --sync, push, create, verify)."""
        ...

    # --- CRUD ---
    def create(self, name: str, *, type: str = "session", parent: str | None = None) -> KEngramManifest:
    def get(self, kengram_id: str) -> KEngramManifest:  # raises NotFoundError
    def get_active(self) -> KEngramManifest:  # raises NotFoundError
    def list(self) -> list[dict]:
    def delete(self, kengram_id: str) -> bool:
    def set_active(self, kengram_id: str) -> None:
    def update_summary(self, kengram_id: str, summary: str) -> KEngramManifest:

    # --- Pin operations ---
    def pin(
        self, kengram_id: str, uuid: str, *,
        name: str = "", summary: str = "", labels: list[str] | None = None,
        fetch_from_kg: bool = True,
    ) -> KEngramManifest:
        """Pin entity to kEngram. If name not provided and fetch_from_kg=True,
        fetches metadata from KG. The CLI's --search flag is NOT handled here —
        CLI calls kg.search() separately, lets user pick, then calls pin()."""

    def unpin(self, kengram_id: str, uuid: str) -> KEngramManifest:

    def add_edge(
        self, kengram_id: str, source_uuid: str, target_uuid: str,
        name: str, fact: str = "", *, sync_to_kg: bool = True,
    ) -> dict:
        """Add edge to kEngram. When sync_to_kg=True, also creates in KG.
        Returns: {"kengram": manifest, "kg_synced": bool, "warnings": [...]}"""

    # --- Batch ---
    def batch(
        self, kengram_id: str, changeset: dict, *,
        sync_to_kg: bool = False, export_canvas: bool = False,
    ) -> dict:
        """Apply a batch changeset (nodes + edges) to kEngram.
        When sync_to_kg=True, pushes entities to KG first to get real UUIDs,
        then syncs edges. When export_canvas=True, exports canvas after.
        Returns: {"kengram": manifest, "nodes_added": int, "edges_added": int,
                  "generated_uuids": {name: uuid}, "kg_push_failures": [...]}"""

    # --- Merge ---
    def merge(self, target_id: str, source_id: str) -> KEngramManifest:

    # --- Verify ---
    def verify(self, kengram_id: str, *, local_only: bool = False) -> dict:
        """Verify integrity — hash comparison + KG sync status.
        Returns full result including: status, merkle_root, recomputed_root,
        nodes (per-node status), canvas_modified count, profile_hash_status,
        plan_structure (orphans, cycles)."""

    # --- Export ---
    def export(
        self, kengram_id: str, *,
        format: str = "canvas",
        serialization: str = "turtle",
    ) -> str:
        """Export kEngram. format: "canvas"|"plan"|"owl".
        Returns file path of exported file."""

    # --- Push (NEW — was missing from v1) ---
    def push(
        self, kengram_id: str, *,
        changes: dict | None = None,
    ) -> dict:
        """Push local-only nodes and edges to canonical KG.
        Handles: entity creation, UUID remapping, edge migration,
        stale edge cleanup, and canvas change processing.
        Returns: {"nodes_pushed": int, "edges_pushed": int, "nodes_updated": int,
                  "nodes_created": int, "edges_created": int, "merkle_root": str}"""

    # --- Repin (NEW — was missing from v1) ---
    def repin(self, kengram_id: str, uuid: str) -> dict:
        """Re-fetch entity from KG and update hash in kEngram.
        Returns: {"changed": bool, "merkle_root": str}"""

    # --- Import OWL (NEW — was missing from v1) ---
    def import_owl(
        self, kengram_id: str, file_path: str, profile_id: str,
    ) -> dict:
        """Import entities from an OWL/RDF file using inverted profile mappings.
        Returns: {"nodes_added": int, "merkle_root": str}"""

    # --- Helpers (internal, used by multiple methods) ---
    def _resolve_manifest(self, kengram_id: str) -> KEngramManifest: ...
    def _resolve_name(self, name: str, name_to_uuid: dict, manifest: KEngramManifest) -> str | None: ...
    def _check_canvas_diff(self, manifest: KEngramManifest) -> dict: ...
    def _verify_for_export(self, manifest: KEngramManifest) -> dict: ...
```

Key changes from v1:
- `KEngramService` takes `KGService` as a dependency (cross-service coupling made explicit)
- Added `push()`, `repin()`, `import_owl()` — were completely missing
- `verify()` returns the full result dict including canvas_modified, profile_hash_status, plan_structure
- `batch()` takes `sync_to_kg` and `export_canvas` flags, returns detailed result dict
- `add_edge()` takes `sync_to_kg` flag, returns dict with warnings
- `pin()` docs clarify that `--search` is handled in CLI layer (search + pick + pin)
- Helper functions (`_resolve_name`, `_check_canvas_diff`, `_verify_for_export`) move here from commands.py

## OntologyService

```python
class OntologyService:
    """Mixes API calls (ingest, match, generate) with local operations (profiles, attach/detach).
    This is intentional — the ontology domain spans both."""

    # --- API operations (require network) ---
    def ingest(self, ontology_path: str, ontology_id: str) -> dict:
    def match_labels(self, ontology_id: str, threshold: float = 0.7) -> list[dict]:
    def generate_profile(self, ontology_id: str, threshold: float = 0.7) -> dict:

    # --- Local profile operations (no network) ---
    def create_profile(self, name: str, kengram_id: str, ontology_id: str, threshold: float = 0.7) -> OntologyProfile:
    def attach_profile(self, kengram_id: str, profile_id: str) -> KEngramManifest:
    def detach_profile(self, kengram_id: str, profile_id: str) -> KEngramManifest:
    def list_profiles(self) -> list[dict]:
    def get_profile(self, profile_id: str) -> OntologyProfile:
    def delete_profile(self, profile_id: str) -> bool:
```

## HTTP Layer (sdk/http.py)

Replaces `api.py`. No more `sys.exit()`, no `quiet` mode hack — all consumers handle exceptions.

```python
def _post(config: BonfiresConfig, path: str, body: dict) -> dict:
    """POST to API. Raises APIError/NotFoundError/AuthenticationError."""
    ...

def _get(config: BonfiresConfig, path: str, params: dict | None = None) -> dict:
    """GET from API. Raises APIError/NotFoundError/AuthenticationError."""
    ...
```

The `kg_client.py` `quiet=True` hack (which bypassed `api_post` to avoid console output) becomes unnecessary — since `_post` raises instead of printing, all callers can simply catch or not catch as needed.

## CLI-Only Commands

These stay in CLI files with no SDK equivalent:
- `init` — interactive setup (prompts for API key, selects bonfire/agent)
- `format-chat`, `format-delve`, `graph` — presentation-only (stdin → Rich output)

## CLI Refactoring Pattern (PR 2)

```python
def _get_client() -> BonfiresClient:
    try:
        return BonfiresClient()  # uses env vars
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Run [bold]bonfire init[/bold] to set up your configuration.")
        sys.exit(1)

# Interactive search stays in CLI — SDK doesn't prompt
@kengram.command()
def pin(uuid, target_id, search_query, ...):
    client = _get_client()
    if search_query:
        results = client.kg.search(search_query)  # SDK call
        # ... display table, click.prompt() ... (CLI-only)
        selected = results["entities"][choice - 1]
        manifest = client.kengrams.pin(target_id, selected["uuid"], ...)
    else:
        manifest = client.kengrams.pin(target_id, uuid, ...)
    # format output with console.print
```

## Deprecation Shims (PR 3)

When deleting `api.py` and `kg_client.py`, leave 5-line shims that import from SDK and emit `DeprecationWarning`:

```python
# api.py (shim)
import warnings
warnings.warn("bonfires.api is deprecated, use bonfires.sdk", DeprecationWarning, stacklevel=2)
from bonfires.sdk.http import _post as api_post, _get as api_get  # noqa: F401
```

## Testing Strategy

- **PR 1 (SDK creation):** New unit tests for each SDK module. Mock at `requests` level. Existing tests are untouched — nothing changed.
- **PR 2 (CLI refactor):** Update ~15 `@patch("bonfires.kengram.commands.kg_client.X")` mock paths. Tests now mock SDK service methods or `sdk.http._post`. Budget ~2h for this migration.
- **PR 3 (deletions):** Verify no remaining imports of deleted modules.

## Verification

1. `pytest` — all existing + new tests pass
2. `bonfire chat "test"` — CLI still works
3. `from bonfires.sdk import BonfiresClient; client = BonfiresClient(); client.kg.search("test")` — works
4. `ruff check` + `ruff format` pass
5. `pip install -e .` installs cleanly
