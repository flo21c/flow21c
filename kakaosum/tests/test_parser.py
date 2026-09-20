import unittest
from datetime import datetime
from pathlib import Path

from kakaosum.models import KIND_DELETED, KIND_EMOTICON, KIND_MEDIA, KIND_SYSTEM, KIND_TEXT
from kakaosum.parser import ParseError, parse_file, parse_text, read_text

ANDROID = """\
플로우마인드 개발팀님과 카카오톡 대화
저장한 날짜 : 2026-09-07 21:10:00

--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:12] 좋은 아침입니다
[김서연] [오후 1:05] 여러 줄로
이어지는 메시지

마지막 줄입니다
[이민호] [오후 1:06] 사진 3장
[이민호] [오후 1:07] (이모티콘)
[김서연] [오후 1:08] 삭제된 메시지입니다.
이민호님이 나갔습니다.
"""

IOS = """\
엄마님과 카카오톡 대화
저장한 날짜 : 2026-09-06 08:00:00

2026년 9월 5일 오전 9:05, 엄마 : 밥은 먹었니
2026년 9월 5일 오후 12:10, 나 : 방금 먹었어요
2026년 9월 5일 오후 12:11, 엄마님이 들어왔습니다.
"""


class ParseAndroidTest(unittest.TestCase):
    def setUp(self):
        self.log = parse_text(ANDROID)

    def test_header(self):
        self.assertEqual(self.log.title, "플로우마인드 개발팀")
        self.assertEqual(self.log.saved_at, datetime(2026, 9, 7, 21, 10, 0))
        self.assertEqual(self.log.source_format, "bracket")

    def test_message_count_and_participants(self):
        self.assertEqual(len(self.log.messages), 6)
        self.assertEqual(self.log.participants, ["박지훈", "김서연", "이민호"])

    def test_timestamps_use_separator_date(self):
        first = self.log.messages[0]
        self.assertEqual(first.dt, datetime(2026, 9, 1, 9, 12))
        self.assertEqual(first.sender, "박지훈")

    def test_afternoon_time_is_24h(self):
        self.assertEqual(self.log.messages[1].dt, datetime(2026, 9, 1, 13, 5))

    def test_multiline_message_is_joined(self):
        text = self.log.messages[1].text
        self.assertEqual(text, "여러 줄로\n이어지는 메시지\n\n마지막 줄입니다")

    def test_kinds(self):
        kinds = [m.kind for m in self.log.messages]
        self.assertEqual(
            kinds, [KIND_TEXT, KIND_TEXT, KIND_MEDIA, KIND_EMOTICON, KIND_DELETED, KIND_SYSTEM]
        )

    def test_system_line_inherits_last_time(self):
        system = self.log.messages[-1]
        self.assertEqual(system.sender, "")
        self.assertEqual(system.dt, datetime(2026, 9, 1, 13, 8))


class ParseIosTest(unittest.TestCase):
    def setUp(self):
        self.log = parse_text(IOS)

    def test_format_and_count(self):
        self.assertEqual(self.log.source_format, "inline")
        self.assertEqual(len(self.log.messages), 3)

    def test_inline_datetime(self):
        self.assertEqual(self.log.messages[0].dt, datetime(2026, 9, 5, 9, 5))
        self.assertEqual(self.log.messages[1].dt, datetime(2026, 9, 5, 12, 10))

    def test_system_line_without_sender(self):
        last = self.log.messages[-1]
        self.assertEqual(last.kind, KIND_SYSTEM)
        self.assertEqual(last.sender, "")


class ParseVariantsTest(unittest.TestCase):
    def test_24h_and_ampm_times(self):
        log = parse_text(
            "--------------- 2026년 1월 2일 금요일 ---------------\n"
            "[A] [13:05] 이십사시간 표기\n"
            "[B] [1:05 PM] 영문 표기\n"
        )
        self.assertEqual(log.messages[0].dt, datetime(2026, 1, 2, 13, 5))
        self.assertEqual(log.messages[1].dt, datetime(2026, 1, 2, 13, 5))

    def test_dotted_date_format(self):
        log = parse_text("2026. 3. 4. 오후 2:00, 홍길동 : 점 찍힌 날짜 형식\n")
        self.assertEqual(log.messages[0].dt, datetime(2026, 3, 4, 14, 0))

    def test_bare_date_separator(self):
        log = parse_text("2026년 5월 6일 수요일\n[A] [오전 8:00] 구분선에 줄이 없는 경우\n")
        self.assertEqual(log.messages[0].dt, datetime(2026, 5, 6, 8, 0))

    def test_midnight_conversion(self):
        log = parse_text(
            "--------------- 2026년 1월 2일 금요일 ---------------\n[A] [오전 12:30] 자정\n"
        )
        self.assertEqual(log.messages[0].dt, datetime(2026, 1, 2, 0, 30))

    def test_sender_with_brackets_in_name(self):
        log = parse_text(
            "--------------- 2026년 1월 2일 금요일 ---------------\n"
            "[김[팀장]] [오전 9:00] 이름에 괄호가 있는 경우\n"
        )
        self.assertEqual(log.messages[0].sender, "김[팀장]")

    def test_empty_input_raises(self):
        with self.assertRaises(ParseError):
            parse_text("이건 그냥 메모장 내용입니다\n두 번째 줄\n")


class ReadFileTest(unittest.TestCase):
    def test_cp949_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cp949.txt"
            path.write_bytes(
                (
                    "--------------- 2026년 1월 2일 금요일 ---------------\n"
                    "[홍길동] [오전 9:00] 윈도우 인코딩\n"
                ).encode("cp949")
            )
            self.assertIn("윈도우 인코딩", read_text(path))
            log = parse_file(path)
            self.assertEqual(log.messages[0].sender, "홍길동")
            self.assertEqual(log.source_name, "cp949.txt")


if __name__ == "__main__":
    unittest.main()
