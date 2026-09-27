import json
import unittest
from pathlib import Path

from clip_selector import build_clips_json, load_transcript


FIXTURE = Path(__file__).parent / "fixtures" / "transcript.json"


class ClipSelectorTests(unittest.TestCase):
    def test_transcript_is_parsed_and_candidates_are_generated(self):
        words = load_transcript(str(FIXTURE))
        self.assertEqual(words[0]["word"], "Nobody")
        self.assertGreater(len(words), 1)

        manifest = build_clips_json(json.loads(FIXTURE.read_text()))
        self.assertGreaterEqual(len(manifest["clips"]), 2)
        for clip in manifest["clips"]:
            self.assertGreaterEqual(clip["duration"], 15)
            self.assertLessEqual(clip["duration"], 55)
            self.assertEqual(clip["duration"], round(clip["end"] - clip["start"], 3))

    def test_manifest_has_exact_upstream_structure(self):
        manifest = build_clips_json(json.loads(FIXTURE.read_text()), source="episode.mp4")
        self.assertEqual(
            set(manifest),
            {"source", "clips", "caption_style", "platform"},
        )
        self.assertEqual(manifest["source"], "episode.mp4")
        self.assertEqual(manifest["caption_style"], "none")
        self.assertEqual(manifest["platform"], "all")
        self.assertTrue(manifest["clips"])
        for clip in manifest["clips"]:
            self.assertEqual(
                set(clip),
                {"id", "title", "start", "end", "duration", "score", "hook"},
            )
            self.assertIsInstance(clip["start"], (int, float))
            self.assertIsInstance(clip["end"], (int, float))
            self.assertLess(clip["start"], clip["end"])
            self.assertGreaterEqual(clip["score"], 0)
            self.assertLessEqual(clip["score"], 100)
            self.assertTrue(clip["id"])

    def test_empty_and_invalid_transcripts_return_empty_manifest(self):
        for transcript in ({}, {"words": []}, {"words": [{"word": "bad", "start": "x", "end": 1}]}):
            manifest = build_clips_json(transcript)
            self.assertEqual(manifest["clips"], [])


if __name__ == "__main__":
    unittest.main()