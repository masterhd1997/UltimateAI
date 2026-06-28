import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.asset_library import AssetLibrary


class AssetLibraryTests(unittest.TestCase):
    def write_manifest(self, temp_dir, data):
        manifest = Path(temp_dir) / "manifest.json"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return manifest

    def test_selects_assets_by_genre_and_style(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "static-hit",
                            "type": "sound",
                            "path": "sounds/static-hit.wav",
                            "genres": ["horror"],
                            "styles": ["horror"],
                            "license": "owned",
                        },
                        {
                            "id": "punch-zoom",
                            "type": "effect",
                            "path": "",
                            "genres": ["general"],
                            "styles": ["hype"],
                            "license": "built-in",
                        },
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual([asset["id"] for asset in assets], ["static-hit"])

    def test_selects_assets_when_genre_or_style_matches(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "genre-only",
                            "type": "sound",
                            "path": "",
                            "genres": ["horror"],
                            "styles": ["cinematic"],
                            "license": "owned",
                        },
                        {
                            "id": "style-only",
                            "type": "effect",
                            "path": "",
                            "genres": ["general"],
                            "styles": ["horror"],
                            "license": "built-in",
                        },
                        {
                            "id": "no-match",
                            "type": "caption",
                            "path": "",
                            "genres": ["racing"],
                            "styles": ["hype"],
                            "license": "licensed",
                        },
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual([asset["id"] for asset in assets], ["genre-only", "style-only"])

    def test_respects_positive_limit(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "first",
                            "type": "effect",
                            "path": "",
                            "genres": ["horror"],
                            "styles": ["horror"],
                            "license": "owned",
                        },
                        {
                            "id": "second",
                            "type": "effect",
                            "path": "",
                            "genres": ["horror"],
                            "styles": ["horror"],
                            "license": "licensed",
                        },
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror", limit=1)
            self.assertEqual([asset["id"] for asset in assets], ["first"])

    def test_blank_genre_and_style_default_to_general_and_hype(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "default-genre",
                            "type": "effect",
                            "path": "",
                            "genres": ["general"],
                            "styles": ["cinematic"],
                            "license": "owned",
                        },
                        {
                            "id": "default-style",
                            "type": "effect",
                            "path": "",
                            "genres": ["horror"],
                            "styles": ["hype"],
                            "license": "built-in",
                        },
                        {
                            "id": "unmatched",
                            "type": "effect",
                            "path": "",
                            "genres": ["horror"],
                            "styles": ["cinematic"],
                            "license": "licensed",
                        },
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="", style="")
            self.assertEqual(
                [asset["id"] for asset in assets], ["default-genre", "default-style"]
            )

    def test_rejects_assets_without_safe_license(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "unsafe",
                            "type": "image",
                            "path": "memes/unsafe.png",
                            "genres": ["funny"],
                            "styles": ["funny"],
                            "license": "unknown",
                        }
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="funny", style="funny")
            self.assertEqual(assets, [])

    def test_missing_manifest_returns_no_assets(self):
        with TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "missing.json"
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual(assets, [])

    def test_respects_zero_limit(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        {
                            "id": "static-hit",
                            "type": "sound",
                            "path": "sounds/static-hit.wav",
                            "genres": ["horror"],
                            "styles": ["horror"],
                            "license": "owned",
                        }
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror", limit=0)
            self.assertEqual(assets, [])

    def test_invalid_json_manifest_returns_no_assets(self):
        with TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text("{", encoding="utf-8")
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual(assets, [])

    def test_non_dict_root_returns_no_assets(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(temp_dir, ["not", "a", "dict"])
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual(assets, [])

    def test_non_list_assets_returns_no_assets(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(temp_dir, {"assets": {"id": "bad"}})
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual(assets, [])

    def test_skips_malformed_asset_records_and_list_fields(self):
        with TemporaryDirectory() as temp_dir:
            manifest = self.write_manifest(
                temp_dir,
                {
                    "assets": [
                        "bad-record",
                        {
                            "id": "bad-genres",
                            "type": "effect",
                            "path": "",
                            "genres": "horror",
                            "styles": [],
                            "license": "owned",
                        },
                        {
                            "id": "bad-styles",
                            "type": "effect",
                            "path": "",
                            "genres": [],
                            "styles": {"name": "horror"},
                            "license": "owned",
                        },
                        {
                            "id": "valid",
                            "type": "effect",
                            "path": "",
                            "genres": ["horror"],
                            "styles": [],
                            "license": "public-domain",
                        },
                    ]
                },
            )
            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")
            self.assertEqual([asset["id"] for asset in assets], ["valid"])
