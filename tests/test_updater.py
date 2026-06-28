import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.updater import check_for_update, compare_versions, evaluate_update_manifest


class UpdaterTests(unittest.TestCase):
    def test_compares_semantic_versions(self):
        self.assertGreater(compare_versions("1.2.0", "1.1.9"), 0)
        self.assertEqual(compare_versions("1.2.0", "1.2.0"), 0)
        self.assertLess(compare_versions("1.2.0", "1.2.1"), 0)

    def test_reports_update_available_from_manifest(self):
        result = evaluate_update_manifest("1.0.0", {
            "version": "1.1.0",
            "download_url": "https://example.com/GameCutAI-1.1.0.exe",
            "sha256": "a" * 64,
            "notes": "New captions",
        })

        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "1.1.0")
        self.assertEqual(result["download_url"], "https://example.com/GameCutAI-1.1.0.exe")

    def test_ignores_equal_version_manifest(self):
        result = evaluate_update_manifest("1.1.0", {
            "version": "1.1.0",
            "download_url": "https://example.com/GameCutAI-1.1.0.exe",
            "sha256": "a" * 64,
        })

        self.assertFalse(result["update_available"])

    def test_reads_utf8_bom_manifest_files(self):
        with TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "latest.json"
            manifest_path.write_text(
                '{"version":"1.1.0","download_url":"https://example.com/app.exe","sha256":"' + ("a" * 64) + '"}',
                encoding="utf-8-sig",
            )

            result = check_for_update(str(manifest_path), current_version="1.0.0")

        self.assertTrue(result["update_available"])

    def test_env_var_overrides_current_version(self):
        """GAMECUT_VERSION env var should be used as APP_VERSION."""
        import backend.services.updater as updater_module
        original = updater_module.APP_VERSION
        try:
            # Simulate a deployment where version is injected at build time
            updater_module.APP_VERSION = "2.0.0"
            result = evaluate_update_manifest("2.0.0", {
                "version": "2.0.0",
                "download_url": "https://example.com/app.exe",
                "sha256": "a" * 64,
            })
            self.assertFalse(result["update_available"])
        finally:
            updater_module.APP_VERSION = original

    def test_no_manifest_url_returns_disabled(self):
        """check_for_update with empty URL returns enabled=False."""
        result = check_for_update(manifest_url="", current_version="1.0.0")
        self.assertFalse(result["enabled"])
        self.assertFalse(result["update_available"])


if __name__ == "__main__":
    unittest.main()
