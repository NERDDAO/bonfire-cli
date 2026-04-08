"""BonfiresClient — main entry point for the Bonfires SDK."""

from __future__ import annotations

from trimtab.db import TrimTabDB

from bonfires.sdk.agents import AgentService
from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import ConfigError
from bonfires.sdk.kg import KGService
from bonfires.sdk.kengram import KEngramService
from bonfires.sdk.ontology import OntologyService
from bonfires.sdk.trimtab import TrimtabService


class BonfiresClient:
    """Programmatic access to the Bonfires AI API.

    Usage::

        # Option A: explicit params (falls back to env vars for missing ones)
        client = BonfiresClient(api_key="...", bonfire_id="...", agent_id="...")

        # Option B: pre-built config
        config = BonfiresConfig.from_env()
        client = BonfiresClient(config=config)

        # Option C: all from env vars / dotenv
        client = BonfiresClient()

    Services are accessed as attributes::

        client.kg.search("query")
        client.agents.chat("hello")
        client.kengrams.create("my-kengram")
        client.ontology.list_profiles()
        client.trimtab.search("dark crypt", grammar="locations")
        client.db  # local TrimTabDB instance for grammar operations
    """

    kg: KGService
    agents: AgentService
    kengrams: KEngramService
    ontology: OntologyService
    db: TrimTabDB
    trimtab: TrimtabService

    def __init__(
        self,
        *,
        config: BonfiresConfig | None = None,
        api_key: str | None = None,
        bonfire_id: str | None = None,
        agent_id: str | None = None,
        api_url: str | None = None,
        vault_dir: str | None = None,
        db_path: str | None = None,
    ) -> None:
        if config is not None:
            self._config = config
        else:
            self._config = self._build_config(
                api_key=api_key,
                bonfire_id=bonfire_id,
                agent_id=agent_id,
                api_url=api_url,
                vault_dir=vault_dir,
            )

        self.kg = KGService(self._config)
        self.agents = AgentService(self._config)
        self.kengrams = KEngramService(self._config, self.kg)
        self.ontology = OntologyService(self._config, self.kg)
        self.trimtab = TrimtabService(self._config)

        # TrimTabDB — defaults to vault_dir/trimtab.db
        _db_path = db_path or self._default_db_path()
        self.db = TrimTabDB(_db_path)

    def _default_db_path(self) -> str:
        """Default DB path: {vault_dir}/trimtab.db"""
        vault = self._config.vault_dir
        if vault:
            from pathlib import Path
            Path(vault).mkdir(parents=True, exist_ok=True)
            return f"{vault}/trimtab.db"
        return ":memory:"

    @property
    def config(self) -> BonfiresConfig:
        """The resolved configuration."""
        return self._config

    @staticmethod
    def _build_config(
        *,
        api_key: str | None,
        bonfire_id: str | None,
        agent_id: str | None,
        api_url: str | None,
        vault_dir: str | None,
    ) -> BonfiresConfig:
        """Build config by merging explicit params over env-loaded values."""
        try:
            env_config = BonfiresConfig.from_env()
        except ConfigError:
            env_config = None

        has_explicit = any(v is not None for v in (api_key, bonfire_id, agent_id))
        if not has_explicit and env_config is None:
            BonfiresConfig.from_env()

        if env_config is not None:
            return BonfiresConfig(
                api_key=api_key or env_config.api_key,
                bonfire_id=bonfire_id or env_config.bonfire_id,
                agent_id=agent_id or env_config.agent_id,
                api_url=api_url or env_config.api_url,
                vault_dir=vault_dir or env_config.vault_dir,
            )

        if not api_key or not bonfire_id or not agent_id:
            raise ConfigError(
                "api_key, bonfire_id, and agent_id are required when env config is unavailable"
            )
        return BonfiresConfig(
            api_key=api_key,
            bonfire_id=bonfire_id,
            agent_id=agent_id,
            api_url=api_url or "https://tnt-v2.api.bonfires.ai",
            vault_dir=vault_dir or "",
        )
