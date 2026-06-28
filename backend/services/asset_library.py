import json
from pathlib import Path
from typing import Any


SAFE_LICENSES = {"owned", "licensed", "built-in", "public-domain"}


class AssetLibrary:
    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)

    def select_assets(
        self, genre: str, style: str, limit: int = 8
    ) -> list[dict[str, Any]]:
        manifest = self._read_manifest()
        if limit <= 0:
            return []

        selected: list[dict[str, Any]] = []
        normalized_genre = self._normalize_value(genre, default="general")
        normalized_style = self._normalize_value(style, default="hype")

        for asset in manifest["assets"]:
            if not isinstance(asset, dict):
                continue

            asset_genres = self._normalize_list_field(asset.get("genres"))
            asset_styles = self._normalize_list_field(asset.get("styles"))
            if asset_genres is None or asset_styles is None:
                continue

            license_name = self._normalize_value(asset.get("license", ""), default="")
            if license_name not in SAFE_LICENSES:
                continue

            if normalized_genre not in asset_genres and normalized_style not in asset_styles:
                continue

            selected.append(asset)
            if len(selected) >= limit:
                break

        return selected

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"assets": []}

        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"assets": []}

        if not isinstance(manifest, dict):
            return {"assets": []}

        assets = manifest.get("assets", [])
        if not isinstance(assets, list):
            return {"assets": []}

        return {"assets": assets}

    @staticmethod
    def _normalize_value(value: Any, default: str) -> str:
        if not value:
            return default
        return str(value).lower()

    @classmethod
    def _normalize_list_field(cls, values: Any) -> set[str] | None:
        if not isinstance(values, list):
            return None
        if not all(isinstance(value, str) for value in values):
            return None
        return {cls._normalize_value(value, default="") for value in values}
