"""Offline tests: the HTTP call is replaced with recorded result rows from the tool."""
import io
import json
import unittest
from unittest import mock

import youtube_transcript_cloud as ytc

ROWS = [
    {"videoId": "jNQXAC9IVRw", "title": "Me at the zoo", "transcriptAvailable": True, "captionType": "manual",
     "languageCode": "en", "language": "English", "languageMatched": True, "coveragePct": 61.2,
     "text": "(intriguing music) - Hi.",
     "segments": [{"start": 0.68, "duration": 2.917, "text": "(intriguing music)"},
                  {"start": 14.762, "duration": 0.833, "text": "- Hi."}]},
    {"videoId": "2JK7NMfvZTY", "transcriptAvailable": False, "unavailableReason": "no_captions",
     "unavailableMessage": "This video has no captions.", "segments": []},
]


def answer(rows):
    return mock.patch.object(ytc.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(rows).encode()))


class VideoId(unittest.TestCase):
    def test_forms(self):
        for s in ("jNQXAC9IVRw", "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=3", "https://youtu.be/jNQXAC9IVRw",
                  "https://www.youtube.com/shorts/jNQXAC9IVRw", "https://www.youtube.com/embed/jNQXAC9IVRw"):
            self.assertEqual(ytc.video_id(s), "jNQXAC9IVRw")

    def test_rejects_junk(self):
        with self.assertRaises(ValueError):
            ytc.video_id("https://example.com/watch")


class Client(unittest.TestCase):
    def setUp(self):
        self.client = ytc.TranscriptClient(token="test-token")

    def test_fetch_maps_snippets(self):
        with answer(ROWS[:1]) as urlopen:
            t = self.client.fetch("https://youtu.be/jNQXAC9IVRw")
        req = urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(json.loads(req.data)["videos"], ["https://www.youtube.com/watch?v=jNQXAC9IVRw"])
        self.assertFalse(t.is_generated)
        self.assertEqual(len(t), 2)
        self.assertEqual(t.to_raw_data()[1], {"text": "- Hi.", "start": 14.762, "duration": 0.833})

    def test_unavailable_raises_with_reason(self):
        with answer(ROWS[1:]), self.assertRaises(ytc.TranscriptUnavailable) as e:
            self.client.fetch("2JK7NMfvZTY")
        self.assertEqual(e.exception.reason, "no_captions")

    def test_fetch_many_keeps_misses(self):
        with answer(ROWS):
            out = self.client.fetch_many(["jNQXAC9IVRw", "2JK7NMfvZTY", "jNQXAC9IVRw"])
        self.assertIsInstance(out["jNQXAC9IVRw"], ytc.Transcript)
        self.assertIsInstance(out["2JK7NMfvZTY"], ytc.TranscriptUnavailable)

    def test_no_token(self):
        with mock.patch.dict("os.environ", {}, clear=True), self.assertRaises(ytc.TranscriptError):
            ytc.TranscriptClient()


if __name__ == "__main__":
    unittest.main()
