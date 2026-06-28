import unittest
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_creates_project_with_metadata(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))

            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )

            project_path = Path(temp_dir) / "projects" / project["id"] / "project.json"
            self.assertIsNotNone(datetime.fromisoformat(project["created_at"]).tzinfo)
            self.assertIsNotNone(datetime.fromisoformat(project["updated_at"]).tzinfo)
            self.assertEqual(set(project), {
                "id",
                "file_name",
                "source_path",
                "options",
                "status",
                "created_at",
                "updated_at",
                "edit_plan",
                "export_path",
            })
            self.assertEqual(project["file_name"], "input.mp4")
            self.assertEqual(project["options"]["game_name"], "Valorant")
            self.assertEqual(project["status"], "created")
            self.assertTrue(project_path.exists())

    def test_gets_persisted_project(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )

            loaded = ProjectStore(Path(temp_dir)).get_project(project["id"])

            self.assertEqual(loaded, project)

    def test_updates_project_after_render(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )

            updated = store.update_project(project["id"], {
                "status": "completed",
                "export_path": "C:/exports/input_hype.mp4",
                "edit_plan": {"cuts": [{"start": 0, "end": 12}]},
            })
            reloaded = ProjectStore(Path(temp_dir)).get_project(project["id"])

            self.assertEqual(updated["status"], "completed")
            self.assertEqual(updated["export_path"], "C:/exports/input_hype.mp4")
            self.assertEqual(updated["edit_plan"], {"cuts": [{"start": 0, "end": 12}]})
            self.assertEqual(reloaded["status"], "completed")
            self.assertEqual(reloaded["export_path"], "C:/exports/input_hype.mp4")
            self.assertEqual(reloaded["edit_plan"], {"cuts": [{"start": 0, "end": 12}]})

    def test_update_project_preserves_id_when_changes_include_id(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )
            replacement_id = "f" * 32

            updated = store.update_project(project["id"], {
                "id": replacement_id,
                "status": "completed",
            })
            reloaded = ProjectStore(Path(temp_dir)).get_project(project["id"])

            self.assertEqual(updated["id"], project["id"])
            self.assertEqual(reloaded["id"], project["id"])
            self.assertEqual(reloaded["status"], "completed")
            self.assertFalse((Path(temp_dir) / "projects" / replacement_id).exists())

    def test_update_unknown_project_raises_key_error(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))

            with self.assertRaises(KeyError):
                store.update_project("missing", {"status": "completed"})

    def test_get_project_returns_none_for_invalid_project_id(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            outside_path = Path(temp_dir) / "outside" / "project.json"
            outside_path.parent.mkdir(parents=True)
            outside_path.write_text(json.dumps({
                "id": "../outside",
                "updated_at": datetime.now().isoformat(),
            }), encoding="utf-8")

            self.assertIsNone(store.get_project("../outside"))
            self.assertIsNone(store.get_project("not-a-uuid-hex"))

    def test_update_project_raises_key_error_for_invalid_project_id(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            outside_path = Path(temp_dir) / "outside" / "project.json"
            outside_path.parent.mkdir(parents=True)
            outside_path.write_text(json.dumps({
                "id": "../outside",
                "status": "created",
                "updated_at": datetime.now().isoformat(),
            }), encoding="utf-8")

            with self.assertRaises(KeyError):
                store.update_project("../outside", {"status": "completed"})

            saved = json.loads(outside_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "created")

    def test_lists_recent_projects_newest_first(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            first = store.create_project(
                source_path="C:/videos/first.mp4",
                file_name="first.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )
            second = store.create_project(
                source_path="C:/videos/second.mp4",
                file_name="second.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )

            recent = store.list_recent_projects(limit=5)

            self.assertEqual([project["id"] for project in recent], [second["id"], first["id"]])

    def test_list_recent_projects_ignores_corrupted_project_files(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )
            corrupted_path = Path(temp_dir) / "projects" / "corrupted" / "project.json"
            corrupted_path.parent.mkdir(parents=True)
            corrupted_path.write_text("{not json", encoding="utf-8")

            recent = store.list_recent_projects(limit=5)

            self.assertEqual([item["id"] for item in recent], [project["id"]])

    def test_list_recent_projects_ignores_valid_json_with_invalid_updated_at(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )
            missing_updated_at = Path(temp_dir) / "projects" / ("a" * 32) / "project.json"
            integer_updated_at = Path(temp_dir) / "projects" / ("b" * 32) / "project.json"
            invalid_updated_at = Path(temp_dir) / "projects" / ("c" * 32) / "project.json"
            missing_updated_at.parent.mkdir(parents=True)
            integer_updated_at.parent.mkdir(parents=True)
            invalid_updated_at.parent.mkdir(parents=True)
            missing_updated_at.write_text('{"id":"' + ("a" * 32) + '"}', encoding="utf-8")
            integer_updated_at.write_text(
                '{"id":"' + ("b" * 32) + '","updated_at":123}',
                encoding="utf-8",
            )
            invalid_updated_at.write_text(
                '{"id":"' + ("c" * 32) + '","updated_at":"not an iso timestamp"}',
                encoding="utf-8",
            )

            recent = store.list_recent_projects(limit=5)

            self.assertEqual([item["id"] for item in recent], [project["id"]])


if __name__ == "__main__":
    unittest.main()
