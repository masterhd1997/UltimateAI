import unittest

from backend.services.edit_plan import create_edit_plan


class EditPlanTests(unittest.TestCase):
    def test_creates_plan_with_clip_effects_and_captions(self):
        plan = create_edit_plan(
            options={
                "game_name": "Resident Evil",
                "style": "horror",
                "target_duration": 45,
                "add_subtitles": True,
                "add_effects": True,
            },
            highlights=[2.0, 19.5],
            research={"genre": "horror", "creator_targets": ["Markiplier", "IGP"]},
        )

        self.assertEqual(plan["target_duration"], 45)
        self.assertEqual(plan["genre"], "horror")
        self.assertEqual(plan["creator_targets"], ["Markiplier", "IGP"])
        self.assertGreaterEqual(len(plan["clips"]), 1)
        self.assertTrue(plan["captions_enabled"])
        self.assertIn("suspense hold", plan["effects"])

    def test_defaults_to_uploaded_gameplay_when_research_is_empty(self):
        plan = create_edit_plan(
            options={"game_name": "Gameplay", "style": "hype", "target_duration": 30},
            highlights=[],
            research=None,
        )

        self.assertEqual(plan["genre"], "general")
        self.assertEqual(plan["clips"][0]["start"], 0.0)
        self.assertEqual(plan["clips"][0]["end"], 30.0)


if __name__ == "__main__":
    unittest.main()
