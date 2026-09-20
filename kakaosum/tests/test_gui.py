"""창(GUI) 모듈에서 창이 없어도 동작하는 부분에 대한 테스트.

위젯 자체는 tkinter 가 있는 환경에서만 뜨므로, 여기서는 요약을 만드는
순수 함수만 확인한다. (모듈 import 가 tkinter 없이도 되는지도 함께 본다)
"""

import tempfile
import unittest
from pathlib import Path

from kakaosum.gui import Options, build_summary, suggested_output
from kakaosum.parser import ParseError

CHAT = """\
개발팀님과 카카오톡 대화

--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:00] 9월 20일에 출시하는 걸로 하죠
[김서연] [오전 9:05] 제 번호는 010-1234-5678 입니다
--------------- 2026년 9월 5일 토요일 ---------------
[박지훈] [오전 10:00] 문서 올렸습니다
"""


class GuiCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "대화.txt"
        self.path.write_text(CHAT, encoding="utf-8")

    def test_default_summary(self):
        text = build_summary(self.path, Options())
        self.assertIn("# 카카오톡 대화 요약", text)
        self.assertIn("결정된 것", text)

    def test_last_days_option(self):
        text = build_summary(self.path, Options(last_days=1, group="none"))
        self.assertIn("2026-09-05", text)
        self.assertNotIn("9월 20일에 출시하는 걸로 하죠", text)

    def test_mask_and_redact(self):
        text = build_summary(self.path, Options(mask=True, redact=True))
        self.assertIn("참여자 A", text)
        self.assertNotIn("박지훈", text)
        self.assertNotIn("1234-5678", text)

    def test_json_format(self):
        import json

        json.loads(build_summary(self.path, Options(fmt="json")))

    def test_unreadable_file_raises(self):
        junk = Path(self.tmp.name) / "메모.txt"
        junk.write_text("그냥 메모입니다\n", encoding="utf-8")
        with self.assertRaises(ParseError):
            build_summary(junk, Options())

    def test_filtered_to_empty_raises(self):
        only_system = Path(self.tmp.name) / "알림만.txt"
        only_system.write_text(
            "--------------- 2026년 9월 1일 화요일 ---------------\n이민호님이 나갔습니다.\n",
            encoding="utf-8",
        )
        with self.assertRaises(ParseError):
            build_summary(only_system, Options(no_system=True))

    def test_suggested_output_names(self):
        self.assertEqual(suggested_output("/tmp/대화.txt").name, "대화_요약.md")
        self.assertEqual(suggested_output("/tmp/대화.txt", "text").name, "대화_요약.txt")
        self.assertEqual(suggested_output("/tmp/대화.txt", "json").name, "대화_요약.json")


if __name__ == "__main__":
    unittest.main()
