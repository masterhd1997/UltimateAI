import base64
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import gui
from backend.services.editing import (
    build_caption_events,
    build_filter_chain,
    normalize_edit_options,
)
from backend.services.edit_plan import create_edit_plan


class EditingOptionsTests(unittest.TestCase):
    def test_normalizes_customer_edit_options(self):
        options = normalize_edit_options({
            "game_name": "  Valorant  ",
            "style": "cinematic",
            "target_duration": "45",
            "add_subtitles": True,
            "add_effects": False,
            "use_whisper": True,
        })

        self.assertEqual(options["game_name"], "Valorant")
        self.assertEqual(options["style"], "cinematic")
        self.assertEqual(options["target_duration"], 45)
        self.assertTrue(options["add_subtitles"])
        self.assertFalse(options["add_effects"])
        self.assertTrue(options["use_whisper"])

    def test_builds_filters_from_effect_and_caption_toggles(self):
        options = normalize_edit_options({
            "game_name": "Minecraft",
            "style": "hype",
            "target_duration": 60,
            "add_subtitles": True,
            "add_effects": True,
        })

        filters = build_filter_chain(options, "C:/Users/Test/AppData/Local/GameCutAI/exports/job_subs.ass")

        self.assertIn("eq=", filters)
        self.assertIn("fade=t=in", filters)
        self.assertIn("ass=", filters)

    def test_caption_events_include_game_and_style(self):
        options = normalize_edit_options({
            "game_name": "Fortnite",
            "style": "funny",
            "add_subtitles": True,
        })

        captions = build_caption_events(options, 30)

        text = " ".join(caption["text"] for caption in captions)
        self.assertIn("Fortnite", text)
        self.assertIn("FUNNY", text)


class EditPlanIntegrationTests(unittest.TestCase):
    def test_edit_plan_result_contains_project_save_fields(self):
        options = normalize_edit_options({
            "game_name": "Minecraft",
            "style": "funny",
            "target_duration": 20,
            "add_subtitles": True,
            "add_effects": True,
        })

        plan = create_edit_plan(
            options,
            [4.0],
            {"genre": "sandbox", "creator_targets": ["Drae"]},
        )

        self.assertEqual(plan["game_name"], "Minecraft")
        self.assertEqual(plan["clips"][0]["start"], 4.0)
        self.assertTrue(plan["captions_enabled"])


class DesktopRenderingWiringTests(unittest.TestCase):
    def test_native_file_selection_creates_project_and_queues_path_render(self):
        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                return ["C:/videos/gameplay.mp4"]

        class FakeProjectStore:
            def __init__(self):
                self.created = []

            def create_project(self, source_path, file_name, options):
                self.created.append((source_path, file_name, options))
                return {"id": "project-123"}

        class FakeThread:
            instances = []

            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.started = False
                FakeThread.instances.append(self)

            def start(self):
                self.started = True

        project_store = FakeProjectStore()
        controller = gui.NativeAppController()
        options = json.dumps({"game_name": "  Valorant  ", "style": "cinematic", "target_duration": 45})

        with patch.object(gui.webview, "windows", [FakeWindow()]):
            with patch.object(gui, "PROJECT_STORE", project_store):
                with patch.object(gui.threading, "Thread", FakeThread):
                    queued = json.loads(controller.select_video_file(options))

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(project_store.created, [
            (
                "C:/videos/gameplay.mp4",
                "gameplay.mp4",
                {
                    "game_name": "Valorant",
                    "style": "cinematic",
                    "target_duration": 45,
                    "add_subtitles": True,
                    "add_effects": True,
                    "use_whisper": False,
                    "audience": [],
                },
            )
        ])
        self.assertEqual(FakeThread.instances[0].args[1], "C:/videos/gameplay.mp4")
        self.assertEqual(FakeThread.instances[0].args[3], "project-123")
        self.assertTrue(FakeThread.instances[0].started)

    def test_malformed_upload_options_fail_before_writing_upload(self):
        with TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir) / "uploads"
            upload_dir.mkdir()
            payload = "data:video/mp4;base64," + base64.b64encode(b"video").decode("ascii")
            controller = gui.NativeAppController()

            with patch.object(gui, "UPLOAD_DIR", upload_dir):
                with self.assertRaises(json.JSONDecodeError):
                    controller.process_video_upload("sample.mp4", payload, "{not-json")

            self.assertEqual(list(upload_dir.iterdir()), [])

    def test_direct_process_video_edit_without_project_id_still_queues_job(self):
        class FakeThread:
            instances = []

            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.started = False
                FakeThread.instances.append(self)

            def start(self):
                self.started = True

        controller = gui.NativeAppController()

        with patch.object(gui.threading, "Thread", FakeThread):
            queued = json.loads(controller.process_video_edit("C:/missing/input.mp4", json.dumps({})))

        self.assertEqual(queued["status"], "queued")
        self.assertIn(queued["job_id"], controller._active_jobs)
        self.assertEqual(controller._active_jobs[queued["job_id"]]["status"], "processing")
        self.assertEqual(FakeThread.instances[0].args[3], None)
        self.assertTrue(FakeThread.instances[0].started)

    def test_project_update_failure_does_not_mask_render_success(self):
        class FailingProjectStore:
            def update_project(self, project_id, changes):
                raise OSError("project store unavailable")

        controller = gui.NativeAppController()
        job = {}
        edit_plan = {"clips": [{"start": 0.0, "end": 10.0}]}

        with patch.object(gui, "PROJECT_STORE", FailingProjectStore()):
            controller._complete_render_success(job, "project-1", "C:/exports/out.mp4", edit_plan)

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress"], 100)
        self.assertEqual(job["result"]["export_path"], "C:/exports/out.mp4")
        self.assertEqual(job["result"]["project_id"], "project-1")
        self.assertEqual(job["result"]["edit_plan"], edit_plan)
        self.assertIn("project_warning", job["result"])


if __name__ == "__main__":
    unittest.main()
