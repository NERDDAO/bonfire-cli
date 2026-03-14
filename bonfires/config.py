"""Configuration management for Bonfires CLI.

Config is loaded from (in priority order):
1. Environment variables
2. ~/.config/bonfires/config.env
3. .env in the current directory
"""

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from rich.console import Console

console = Console()

CONFIG_DIR = Path.home() / ".config" / "bonfires"
CONFIG_FILE = CONFIG_DIR / "config.env"

REQUIRED_KEYS = {
    "BONFIRE_API_KEY": "API key for authentication",
    "BONFIRE_ID": "Your bonfire ID",
    "BONFIRE_AGENT_ID": "Agent ID to interact with",
}

DEFAULT_API_URL = "https://tnt-v2.api.bonfires.ai"


def get_config() -> dict[str, Any]:
    """Load and validate configuration."""
    # Layer 1: defaults
    cfg: dict[str, Any] = {"api_url": DEFAULT_API_URL}

    # Layer 2: global config file
    if CONFIG_FILE.exists():
        file_vals = dotenv_values(CONFIG_FILE)
        cfg.update({k: v for k, v in file_vals.items() if v})

    # Layer 3: local .env (overrides global)
    local_env = Path.cwd() / ".env"
    if local_env.exists():
        file_vals = dotenv_values(local_env)
        cfg.update({k: v for k, v in file_vals.items() if v})

    # Layer 4: environment variables (highest priority)
    cfg["api_url"] = os.environ.get("BONFIRE_API_URL", cfg.get("BONFIRE_API_URL", cfg["api_url"]))
    cfg["bonfire_id"] = os.environ.get("BONFIRE_ID", cfg.get("BONFIRE_ID"))
    cfg["agent_id"] = os.environ.get("BONFIRE_AGENT_ID", cfg.get("BONFIRE_AGENT_ID"))
    cfg["api_key"] = os.environ.get("BONFIRE_API_KEY", cfg.get("BONFIRE_API_KEY"))
    cfg["vault_dir"] = os.environ.get(
        "BONFIRE_VAULT_DIR",
        cfg.get("BONFIRE_VAULT_DIR", str(Path.home() / "Vaults" / "Bonfires" / "vault")),
    )
    cfg["group_id"] = f"{cfg['bonfire_id']}:{cfg['agent_id']}"

    missing = [k for k in ("bonfire_id", "agent_id", "api_key") if not cfg.get(k)]
    if missing:
        console.print(f"[red]Missing config: {', '.join(missing)}[/red]")
        console.print("Run [bold]bonfire init[/bold] to set up your configuration.")
        sys.exit(1)

    return cfg
