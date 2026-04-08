"""Configuration management for Bonfires CLI.

Thin wrapper over bonfires.sdk.config — loads config from env/dotenv,
prints errors and exits on failure (CLI behavior).

Config is loaded from (in priority order):
1. Environment variables
2. ~/.config/bonfires/config.env (from `bonfire init`)
3. .env in the current directory
"""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console

from bonfires.sdk.config import CONFIG_DIR, CONFIG_FILE, BonfiresConfig
from bonfires.sdk.config import _DEFAULT_API_URL as DEFAULT_API_URL
from bonfires.sdk.exceptions import ConfigError

console = Console()


def get_config() -> dict[str, Any]:
    """Load and validate configuration.

    Returns a dict for backward compatibility with existing CLI code.
    Prints error and exits on failure.
    """
    try:
        cfg = BonfiresConfig.from_env()
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Run [bold]bonfire init[/bold] to set up your configuration.")
        sys.exit(1)

    return {
        "api_url": cfg.api_url,
        "bonfire_id": cfg.bonfire_id,
        "agent_id": cfg.agent_id,
        "api_key": cfg.api_key,
        "vault_dir": cfg.vault_dir,
        "group_id": cfg.group_id,
    }


__all__ = ["get_config", "CONFIG_DIR", "CONFIG_FILE", "DEFAULT_API_URL"]
