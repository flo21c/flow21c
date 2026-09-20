import unittest
from datetime import datetime

from kakaosum.analyze import (
    compute_stats,
    find_hits,
    group_hits,
    has_contact_info,
    keywords,
    normalize_token,
    redact,
    tokenize,
)
from kakaosum.parser import parse_text

CHAT = """\
--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:00] 이번 주에 출시 일정을 확정해야 합니다
[김서연] [오전 9:05] 9월 20일에 출시하는 걸로 하죠
[박지훈] [오전 9:06] 좋습니다. 그럼 그렇게 결정하겠습니다
[김서연] [오전 9:10] 배포 문서 정리해주세요
[이민호] [오전 9:20] 예산은 얼마나 될까요?
[박지훈] [오전 9:25] 1,200,000원 정도로 잡고 있습니다
[김서연] [오전 9:30] 자료는 https://example.com/doc 에 있습니다
[이민호] [오후 11:50] 혹시 서버 계정은 누가 관리하나요?
"""


class TokenizeTest(unittest.TestCase):
    def test_strips_josa(self):
        self.assertEqual(normalize_token("가격이"), "가격")
        self.assertEqual(normalize_token("회의실에서"), "회의실")

    def test_drops_verb_forms_and_fillers(self):
        for word in ("했습니다", "합시다", "공유드릴게요", "그리고", "ㅋㅋ", "네"):
            self.assertIsNone(normalize_token(word), word)

    def test_keeps_two_syllable_noun(self):
        self.assertEqual(normalize_token("회의"), "회의")

    def test_number_units_are_dropped(self):
        self.assertNotIn("시에", tokenize("오후 3시에 봅시다"))

    def test_latin_word_is_lowercased(self):
        self.assertIn("png", tokenize("PNG 저장이 안 됩니다"))

    def test_url_is_not_tokenized(self):
        self.assertNotIn("example", tokenize("https://example.com/abc 확인"))


class KeywordTest(unittest.TestCase):
    def test_ranks_by_frequency(self):
        log = parse_text(CHAT)
        words = [k.word for k in keywords(log.messages, top_n=5, min_count=2)]
        self.assertIn("출시", words)

    def test_short_chat_falls_back_to_single_hits(self):
        log = parse_text(
            "--------------- 2026년 9월 1일 화요일 ---------------\n[A] [오전 9:00] 도면 검토\n"
        )
        self.assertTrue(keywords(log.messages, top_n=5))


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.stats = compute_stats(parse_text(CHAT))

    def test_counts(self):
        self.assertEqual(self.stats.speech, 8)
        self.assertEqual(self.stats.system, 0)
        self.assertEqual(len(self.stats.participants), 3)

    def test_share_sums_to_one(self):
        self.assertAlmostEqual(sum(p.share for p in self.stats.participants), 1.0, places=6)

    def test_busiest_day_and_peak_hour(self):
        self.assertEqual(self.stats.busiest_day[0], datetime(2026, 9, 1).date())
        self.assertEqual(self.stats.peak_hour[0], 9)

    def test_questions_counted(self):
        민호 = next(p for p in self.stats.participants if p.name == "이민호")
        self.assertEqual(민호.questions, 2)


class HitsTest(unittest.TestCase):
    def setUp(self):
        self.grouped = group_hits(find_hits(parse_text(CHAT)))

    def _texts(self, key):
        return [h.message.text for h in self.grouped[key]]

    def test_decision_found(self):
        self.assertTrue(any("걸로 하죠" in t for t in self._texts("decision")))

    def test_todo_found(self):
        self.assertIn("배포 문서 정리해주세요", self._texts("todo"))

    def test_schedule_found(self):
        self.assertTrue(any("9월 20일" in t for t in self._texts("schedule")))

    def test_link_found(self):
        self.assertEqual(self.grouped["link"][0].snippet, "https://example.com/doc")

    def test_money_found(self):
        self.assertTrue(any("1,200,000원" in t for t in self._texts("money")))

    def test_unanswered_question_only(self):
        texts = self._texts("question")
        self.assertIn("혹시 서버 계정은 누가 관리하나요?", texts)   # 마지막이라 답이 없음
        self.assertNotIn("예산은 얼마나 될까요?", texts)            # 5분 뒤 답변 있음


class PrivacyTest(unittest.TestCase):
    def test_redact_phone_and_email(self):
        masked = redact("연락처는 010-1234-5678, 메일은 hong@example.com 입니다")
        self.assertNotIn("1234-5678", masked)
        self.assertNotIn("hong@example.com", masked)

    def test_has_contact_info(self):
        log = parse_text(
            "--------------- 2026년 9월 1일 화요일 ---------------\n"
            "[A] [오전 9:00] 제 번호는 010-1234-5678 입니다\n"
        )
        self.assertTrue(has_contact_info(log))


if __name__ == "__main__":
    unittest.main()
