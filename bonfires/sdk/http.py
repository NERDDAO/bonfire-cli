"""HTTP transport layer for the Bonfires SDK.

Replaces bonfires/api.py — raises exceptions instead of sys.exit().
"""

from __future__ import annotations

from typing import Any

import requests

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.exceptions import APIError, AuthenticationError, NotFoundError


def _headers(config: BonfiresConfig) -> dict[str, str]:
    """Return common auth headers."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
        "X-Bonfire-Id": config.bonfire_id,
        "X-Agent-Id": config.agent_id,
    }


def _post(config: BonfiresConfig, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST to the Bonfires API and return parsed JSON.

    Raises APIError, NotFoundError, or AuthenticationError on failure.
    """
    url = f"{config.api_url}{path}"
    try:
        resp = requests.post(url, json=body, headers=_headers(config), timeout=30)
    except requests.RequestException as e:
        raise APIError(f"Connection error: {e}", status_code=0, response_text="") from e
    if not resp.ok:
        text = resp.text[:500]
        if resp.status_code == 404:
            raise NotFoundError(
                f"Not found: {path}",
                status_code=resp.status_code,
                response_text=text,
            )
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {path}",
                status_code=resp.status_code,
                response_text=text,
            )
        raise APIError(
            f"API error {resp.status_code}: {path}",
            status_code=resp.status_code,
            response_text=text,
        )
    return resp.json()


def _put(config: BonfiresConfig, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """PUT to the Bonfires API and return parsed JSON."""
    url = f"{config.api_url}{path}"
    try:
        resp = requests.put(url, json=body, headers=_headers(config), timeout=30)
    except requests.RequestException as e:
        raise APIError(f"Connection error: {e}", status_code=0, response_text="") from e
    if not resp.ok:
        text = resp.text[:500]
        if resp.status_code == 404:
            raise NotFoundError(f"Not found: {path}", status_code=resp.status_code, response_text=text)
        if resp.status_code in (401, 403):
            raise AuthenticationError(f"Authentication failed: {path}", status_code=resp.status_code, response_text=text)
        raise APIError(f"API error {resp.status_code}: {path}", status_code=resp.status_code, response_text=text)
    return resp.json()


def _delete(config: BonfiresConfig, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """DELETE from the Bonfires API and return parsed JSON."""
    url = f"{config.api_url}{path}"
    try:
        resp = requests.delete(url, params=params, headers=_headers(config), timeout=30)
    except requests.RequestException as e:
        raise APIError(f"Connection error: {e}", status_code=0, response_text="") from e
    if not resp.ok:
        text = resp.text[:500]
        if resp.status_code == 404:
            raise NotFoundError(f"Not found: {path}", status_code=resp.status_code, response_text=text)
        if resp.status_code in (401, 403):
            raise AuthenticationError(f"Authentication failed: {path}", status_code=resp.status_code, response_text=text)
        raise APIError(f"API error {resp.status_code}: {path}", status_code=resp.status_code, response_text=text)
    if resp.status_code == 204:
        return {}
    return resp.json()


def _get(
    config: BonfiresConfig,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GET from the Bonfires API and return parsed JSON.

    Raises APIError, NotFoundError, or AuthenticationError on failure.
    """
    url = f"{config.api_url}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(config), timeout=30)
    except requests.RequestException as e:
        raise APIError(f"Connection error: {e}", status_code=0, response_text="") from e
    if not resp.ok:
        text = resp.text[:500]
        if resp.status_code == 404:
            raise NotFoundError(
                f"Not found: {path}",
                status_code=resp.status_code,
                response_text=text,
            )
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {path}",
                status_code=resp.status_code,
                response_text=text,
            )
        raise APIError(
            f"API error {resp.status_code}: {path}",
            status_code=resp.status_code,
            response_text=text,
        )
    return resp.json()
