import unittest

from kakaosum.ai import (
    DEFAULT_MODEL,
    AIError,
    build_transcript,
    split_transcript,
    summarize_with_claude,
)
from kakaosum.parser import parse_text

CHAT = """\
--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:00] 안녕하세요
[김서연] [오전 9:05] 제 번호는 010-1234-5678 입니다
박지훈님이 나갔습니다.
"""


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.log = parse_text(CHAT)

    def test_transcript_shape(self):
        text = build_transcript(self.log)
        self.assertTrue(text.startswith("[2026-09-01]"))
        self.assertIn("09:00 박지훈: 안녕하세요", text)

    def test_system_lines_excluded_by_default(self):
        self.assertNotIn("나갔습니다", build_transcript(self.log))
        self.assertIn("나갔습니다", build_transcript(self.log, include_system=True))

    def test_redact_applies(self):
        self.assertNotIn("1234-5678", build_transcript(self.log, redact=True))

    def test_split_keeps_all_lines(self):
        transcript = build_transcript(self.log)
        chunks = split_transcript(transcript, chunk_chars=20)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            sum(len(c.splitlines()) for c in chunks), len(transcript.splitlines())
        )

    def test_short_transcript_is_single_chunk(self):
        self.assertEqual(len(split_transcript("한 줄", chunk_chars=1000)), 1)

    def test_default_model(self):
        self.assertEqual(DEFAULT_MODEL, "claude-opus-5")

    def test_empty_log_raises_before_any_api_call(self):
        empty = parse_text(CHAT).filtered(senders=["없는사람"])
        with self.assertRaises(AIError):
            summarize_with_claude(empty)


if __name__ == "__main__":
    unittest.main()
