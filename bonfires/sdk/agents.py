"""Agent service for the Bonfires SDK."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bonfires.sdk.config import BonfiresConfig
from bonfires.sdk.http import _delete, _get, _post, _put


class AgentService:
    """Operations on Bonfires agents — CRUD, chat, sync."""

    def __init__(self, config: BonfiresConfig) -> None:
        self._config = config

    # ── CRUD ──

    def create(
        self,
        *,
        name: str,
        username: str,
        context: str,
        platform: str = "matrix",
        is_active: bool = True,
        timezone: str = "UTC",
        deployment_config: dict[str, Any] | None = None,
        agent_features: dict[str, Any] | None = None,
        chat_config: dict[str, Any] | None = None,
        enabled_mcp_tools: list[str] | None = None,
        enabled_skills: list[str] | None = None,
        agent_env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new agent on the configured bonfire.

        Returns the created agent dict with _id, username, name, etc.
        """
        body: dict[str, Any] = {
            "username": username,
            "name": name,
            "context": context,
            "bonfireId": self._config.bonfire_id,
            "isActive": is_active,
            "timezone": timezone,
            "deploymentConfiguration": {
                "platform": platform,
                "bonfireId": self._config.bonfire_id,
                **(deployment_config or {}),
            },
        }
        if agent_features:
            body["agentFeatures"] = agent_features
        if chat_config:
            body["chatConfig"] = chat_config
        if enabled_mcp_tools:
            body["enabledMcpTools"] = enabled_mcp_tools
        if enabled_skills:
            body["enabledSkills"] = enabled_skills
        if agent_env_vars:
            body["agentEnvVars"] = agent_env_vars
        return _post(self._config, "/agents", body=body)

    def get(self, agent_id: str) -> dict[str, Any]:
        """Fetch a single agent by ID."""
        return _get(
            self._config,
            f"/agents/{agent_id}",
            params={"bonfire_id": self._config.bonfire_id},
        )

    def update(self, agent_id: str, **fields: Any) -> dict[str, Any]:
        """Update an existing agent. Pass only the fields to change."""
        return _put(
            self._config,
            f"/agents/{agent_id}",
            body={"bonfire_id": self._config.bonfire_id, **fields},
        )

    def set_env_vars(self, agent_id: str, env_vars: dict[str, str]) -> dict[str, Any]:
        """Set environment variables for an agent."""
        return _put(
            self._config,
            f"/agents/{agent_id}/env-vars",
            body={"variables": env_vars},
        )

    def delete(self, agent_id: str) -> dict[str, Any]:
        """Delete an agent."""
        return _delete(
            self._config,
            f"/agents/{agent_id}",
            params={"bonfire_id": self._config.bonfire_id},
        )

    # ── Chat & Sync ──

    def chat(self, message: str, graph_mode: str = "regenerate") -> dict[str, Any]:
        """Send a message to the bonfire agent. Returns the full response dict."""
        return _post(
            self._config,
            f"/agents/{self._config.agent_id}/chat",
            body={
                "message": message,
                "agent_id": self._config.agent_id,
                "bonfire_id": self._config.bonfire_id,
                "chat_history": [],
                "graph_mode": graph_mode,
            },
        )

    def sync(
        self,
        message: str,
        *,
        chat_id: str = "",
        file_path: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Push context to the KG stack. Optionally ingest a markdown file.

        Args:
            message: The context message to push.
            chat_id: Conversation identifier (e.g. "repo:branch"). Defaults to "sdk:unknown".
            file_path: Path to a .md file to ingest as a document.
            title: Title for the ingested document (derived from filename if omitted).
        """
        if not chat_id:
            chat_id = "sdk:unknown"

        repo = chat_id.split(":")[0] if ":" in chat_id else "unknown"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Step 1: Push to stack. Metadata must live inside the message —
        # StackAddRequest has no top-level metadata field and Pydantic drops
        # unknown keys silently.
        stack_body = {
            "message": {
                "userId": "claude-code",
                "chatId": chat_id,
                "role": "assistant",
                "text": message,
                "timestamp": timestamp,
                "metadata": {
                    "type": "memory-sync",
                    "source": "bonfires-sdk",
                    "repo": repo,
                },
            },
        }
        stack_resp = _post(
            self._config,
            f"/agents/{self._config.agent_id}/stack/add",
            stack_body,
        )

        # Step 2: Process stack
        _post(
            self._config,
            f"/agents/{self._config.agent_id}/stack/process",
            {},
        )

        result: dict[str, Any] = {
            "stack": stack_resp,
            "chat_id": chat_id,
            "repo": repo,
        }

        # Step 3: Ingest file if provided
        if file_path:
            content = Path(file_path).read_text()
            doc_title = (
                title
                or Path(file_path).stem.replace("-", " ").replace("_", " ").title()
            )
            ingest_resp = _post(
                self._config,
                "/ingest_content",
                body={
                    "content": content,
                    "title": doc_title,
                    "bonfire_id": self._config.bonfire_id,
                    "agent_id": self._config.agent_id,
                    "metadata": {
                        "type": "memory-sync",
                        "source": "bonfires-sdk",
                        "repo": repo,
                        "file": file_path,
                    },
                },
            )
            result["document_id"] = ingest_resp.get("document_id", "unknown")

        return result

    def list(self) -> list[dict[str, Any]]:
        """List agents for the configured bonfire."""
        data = _get(
            self._config,
            "/agents",
            params={"bonfire_id": self._config.bonfire_id},
        )
        if isinstance(data, list):
            return data
        return data.get("agents", data.get("data", []))

    def list_bonfires(self) -> list[dict[str, Any]]:
        """List all bonfires."""
        data = _get(self._config, "/bonfires")
        if isinstance(data, list):
            return data
        return data.get("bonfires", data.get("data", []))
