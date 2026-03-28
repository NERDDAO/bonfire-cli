"""Configuration management for the Bonfires SDK.

Config is loaded from (in priority order):
1. Explicit constructor parameters
2. Environment variables
3. ~/.config/bonfires/config.env
4. .env in the current directory
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from bonfires.sdk.exceptions import ConfigError

CONFIG_DIR = Path.home() / ".config" / "bonfires"
CONFIG_FILE = CONFIG_DIR / "config.env"

_DEFAULT_API_URL = "https://tnt-v2.api.bonfires.ai"
_DEFAULT_VAULT_DIR = str(Path.home() / "Vaults" / "Bonfires" / "vault")


@dataclass
class BonfiresConfig:
    """Typed configuration for Bonfires SDK."""

    api_key: str
    bonfire_id: str
    agent_id: str
    api_url: str = _DEFAULT_API_URL
    vault_dir: str = ""
    group_id: str = field(default="", init=True)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ConfigError("api_key is required")
        if not self.bonfire_id:
            raise ConfigError("bonfire_id is required")
        if not self.agent_id:
            raise ConfigError("agent_id is required")
        if not self.group_id:
            self.group_id = f"{self.bonfire_id}:{self.agent_id}"
        if not self.vault_dir:
            raise ConfigError(
                "vault_dir must be configured (set BONFIRE_VAULT_DIR env var)"
            )

    @classmethod
    def from_env(cls) -> BonfiresConfig:
        """Load from env vars + dotenv files.

        Priority: env vars > ~/.config/bonfires/config.env > .env
        Raises ConfigError if required keys are missing.
        """
        merged: dict[str, str] = {}

        # Layer 1: global config file
        if CONFIG_FILE.exists():
            file_vals = dotenv_values(CONFIG_FILE)
            merged.update({k: v for k, v in file_vals.items() if v})

        # Layer 2: local .env (overrides global)
        local_env = Path.cwd() / ".env"
        if local_env.exists():
            file_vals = dotenv_values(local_env)
            merged.update({k: v for k, v in file_vals.items() if v})

        # Layer 3: environment variables (highest priority)
        api_url = os.environ.get(
            "BONFIRE_API_URL", merged.get("BONFIRE_API_URL", _DEFAULT_API_URL)
        )
        bonfire_id = os.environ.get("BONFIRE_ID", merged.get("BONFIRE_ID", ""))
        agent_id = os.environ.get(
            "BONFIRE_AGENT_ID", merged.get("BONFIRE_AGENT_ID", "")
        )
        api_key = os.environ.get("BONFIRE_API_KEY", merged.get("BONFIRE_API_KEY", ""))
        vault_dir = os.environ.get(
            "BONFIRE_VAULT_DIR",
            merged.get("BONFIRE_VAULT_DIR", _DEFAULT_VAULT_DIR),
        )

        missing = []
        if not api_key:
            missing.append("BONFIRE_API_KEY")
        if not bonfire_id:
            missing.append("BONFIRE_ID")
        if not agent_id:
            missing.append("BONFIRE_AGENT_ID")
        if missing:
            raise ConfigError(f"Missing config: {', '.join(missing)}")

        return cls(
            api_key=api_key,
            bonfire_id=bonfire_id,
            agent_id=agent_id,
            api_url=api_url,
            vault_dir=vault_dir,
        )
