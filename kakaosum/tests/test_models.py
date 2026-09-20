import unittest
from datetime import datetime

from kakaosum.models import KIND_SYSTEM, ChatLog, Message
from kakaosum.parser import parse_text

CHAT = """\
--------------- 2026년 9월 1일 화요일 ---------------
[A] [오전 9:00] 첫날 아침
[B] [오후 8:00] 첫날 저녁
--------------- 2026년 9월 3일 목요일 ---------------
[A] [오전 9:00] 사흘째
A님이 나갔습니다.
"""


class ChatLogTest(unittest.TestCase):
    def setUp(self):
        self.log = parse_text(CHAT)

    def test_period(self):
        self.assertEqual(self.log.start, datetime(2026, 9, 1, 9, 0))
        self.assertEqual(self.log.end, datetime(2026, 9, 3, 9, 0))
        self.assertEqual(len(self.log.days), 2)

    def test_speech_excludes_system(self):
        self.assertEqual(len(self.log.speech), 3)
        self.assertEqual(len(self.log.messages), 4)

    def test_filter_by_date(self):
        only_first = self.log.filtered(until=datetime(2026, 9, 1, 23, 59))
        self.assertEqual(len(only_first.messages), 2)

    def test_filter_by_sender(self):
        only_a = self.log.filtered(senders=["A"])
        self.assertEqual({m.sender for m in only_a.messages}, {"A"})

    def test_exclude_system(self):
        self.assertTrue(
            all(m.kind != KIND_SYSTEM for m in self.log.filtered(include_system=False).messages)
        )

    def test_last_days(self):
        recent = self.log.last_days(1)
        self.assertEqual([m.text for m in recent.speech], ["사흘째"])

    def test_by_day_groups(self):
        grouped = self.log.by_day()
        self.assertEqual([len(msgs) for _, msgs in grouped], [2, 2])

    def test_sessions_split_on_long_gap(self):
        self.assertEqual(len(self.log.sessions(gap_minutes=180)), 3)

    def test_masked_renames_everyone(self):
        masked = self.log.masked()
        self.assertEqual(masked.participants, ["참여자 A", "참여자 B"])
        self.assertNotIn("A", {m.sender for m in masked.speech} - {"참여자 A"})

    def test_masked_can_keep_names(self):
        masked = self.log.masked(keep=["A"])
        self.assertIn("A", masked.participants)

    def test_filter_keeps_metadata(self):
        filtered = self.log.filtered(senders=["A"])
        self.assertEqual(filtered.source_format, self.log.source_format)


class MessageTest(unittest.TestCase):
    def test_to_dict_roundtrip_fields(self):
        message = Message(datetime(2026, 1, 1, 12, 0), "홍길동", "안녕", line_no=3)
        data = message.to_dict()
        self.assertEqual(data["datetime"], "2026-01-01T12:00:00")
        self.assertEqual(data["sender"], "홍길동")
        self.assertTrue(message.is_speech)
        self.assertEqual(message.day, message.dt.date())

    def test_empty_log_has_no_period(self):
        empty = ChatLog()
        self.assertIsNone(empty.start)
        self.assertEqual(empty.participants, [])


if __name__ == "__main__":
    unittest.main()
