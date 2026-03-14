"""Vault storage for kEngram manifests.

Manifests are stored as JSON files in vault/kengrams/manifests/.
The active kEngram ID is tracked in vault/kengrams/.active.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bonfires.kengram.manifest import KEngramManifest


class KEngramStorage:
    def __init__(self, vault_dir: str | Path):
        self.vault_dir = Path(vault_dir)
        self.manifests_dir = self.vault_dir / "kengrams" / "manifests"
        self.canvas_dir = self.vault_dir / "kengrams" / "canvas"
        self._active_file = self.vault_dir / "kengrams" / ".active"

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
