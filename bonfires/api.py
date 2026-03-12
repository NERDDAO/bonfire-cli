"""Bonfires API client."""

import sys

import requests
from rich.console import Console
from rich.panel import Panel

console = Console()


def api_headers(cfg):
    """Return common auth headers."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "X-Bonfire-Id": cfg["bonfire_id"],
        "X-Agent-Id": cfg["agent_id"],
    }


def api_post(cfg, path, body):
    """POST to the Bonfires API and return parsed JSON."""
    url = f"{cfg['api_url']}{path}"
    try:
        resp = requests.post(url, json=body, headers=api_headers(cfg), timeout=30)
    except requests.RequestException as e:
        console.print(Panel(str(e), title="Connection Error", border_style="red"))
        sys.exit(1)
    if not resp.ok:
        console.print(Panel(resp.text[:500], title=f"API Error {resp.status_code}", border_style="red"))
        sys.exit(1)
    return resp.json()


def api_get(cfg, path, params=None):
    """GET from the Bonfires API and return parsed JSON."""
    url = f"{cfg['api_url']}{path}"
    try:
        resp = requests.get(url, params=params, headers=api_headers(cfg), timeout=30)
    except requests.RequestException as e:
        console.print(Panel(str(e), title="Connection Error", border_style="red"))
        sys.exit(1)
    if not resp.ok:
        console.print(Panel(resp.text[:500], title=f"API Error {resp.status_code}", border_style="red"))
        sys.exit(1)
    return resp.json()
