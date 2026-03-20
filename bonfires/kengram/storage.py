"""Vault storage for kEngram manifests.

Manifests are stored as JSON files in vault/kengrams/manifests/.
The active kEngram ID is tracked in vault/kengrams/.active.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bonfires.kengram.manifest import KEngramManifest
from bonfires.kengram.ontology_profile import OntologyProfile


class KEngramStorage:
    def __init__(self, vault_dir: str | Path):
        self.vault_dir = Path(vault_dir)
        self.manifests_dir = self.vault_dir / "kengrams" / "manifests"
        self.canvas_dir = self.vault_dir / "kengrams" / "canvas"
        self._active_file = self.vault_dir / "kengrams" / ".active"
        self.profiles_dir = self.vault_dir / "kengrams" / "profiles"
        self.exports_dir = self.vault_dir / "kengrams" / "exports"

    def save(self, manifest: KEngramManifest) -> Path:
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        path = self.manifests_dir / f"{manifest.id}.json"
        path.write_text(json.dumps(manifest.to_dict(), indent=2))
        return path

    def load(self, kengram_id: str) -> KEngramManifest | None:
        path = self.manifests_dir / f"{kengram_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return KEngramManifest.from_dict(data)

    def delete(self, kengram_id: str) -> bool:
        path = self.manifests_dir / f"{kengram_id}.json"
        if path.exists():
            path.unlink()
            if self.get_active() == kengram_id:
                self._active_file.unlink(missing_ok=True)
            return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        if not self.manifests_dir.exists():
            return []
        items = []
        for path in sorted(self.manifests_dir.glob("ke-*.json")):
            data = json.loads(path.read_text())
            items.append({
                "id": data["id"],
                "name": data["name"],
                "type": data["type"],
                "nodes": len(data.get("pinned_nodes", [])),
                "merkle_root": data.get("merkle_root", "")[:16],
                "updated_at": data.get("updated_at", ""),
            })
        return items

    def get_active(self) -> str | None:
        if not self._active_file.exists():
            return None
        return self._active_file.read_text().strip() or None

    def set_active(self, kengram_id: str) -> None:
        self._active_file.parent.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(kengram_id)

    def save_canvas(self, kengram_id: str, canvas_data: dict[str, Any]) -> Path:
        self.canvas_dir.mkdir(parents=True, exist_ok=True)
        path = self.canvas_dir / f"{kengram_id}.canvas"
        path.write_text(json.dumps(canvas_data, indent=2))
        return path

    def save_plan(self, kengram_id: str, name: str | None, markdown: str) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = name.lower().replace(" ", "-")[:50] if name else kengram_id
        filename = f"{date}-{slug}.md"
        plan_dir = self.vault_dir / "kengrams" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        path = plan_dir / filename
        path.write_text(markdown)
        return path

    # ------------------------------------------------------------------
    # Ontology profile storage
    # ------------------------------------------------------------------

    def save_profile(self, profile: OntologyProfile) -> Path:
        """Persist an ontology profile as JSON and return its path."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self.profiles_dir / f"{profile.id}.json"
        path.write_text(json.dumps(profile.to_dict(), indent=2))
        return path

    def load_profile(self, profile_id: str) -> OntologyProfile | None:
        """Load an ontology profile by ID. Returns None if not found."""
        path = self.profiles_dir / f"{profile_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return OntologyProfile.from_dict(data)

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return summary dicts for all stored ontology profiles."""
        if not self.profiles_dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.profiles_dir.glob("profile-*.json")):
            data = json.loads(path.read_text())
            items.append({
                "id": data["id"],
                "name": data["name"],
                "version": data.get("version", ""),
                "namespaces": list(data.get("namespaces", {}).keys()),
            })
        return items

    def load_profiles_for_manifest(self, manifest: KEngramManifest) -> list[OntologyProfile]:
        """Load all profiles referenced by a manifest, in declaration order."""
        profiles: list[OntologyProfile] = []
        for profile_id in manifest.ontology_profiles:
            profile = self.load_profile(profile_id)
            if profile is not None:
                profiles.append(profile)
        return profiles

    # ------------------------------------------------------------------
    # Export storage
    # ------------------------------------------------------------------

    def save_export(self, kengram_id: str, content: str, extension: str) -> Path:
        """Write an export file and return its path.

        ``extension`` should be a bare extension such as ``ttl`` or ``json-ld``.
        The file is named ``{kengram_id}.{extension}`` inside the exports dir.
        """
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        path = self.exports_dir / f"{kengram_id}.{extension}"
        path.write_text(content)
        return path
