import json
import unittest

from kakaosum.parser import parse_text
from kakaosum.render import render, render_markdown, render_text
from kakaosum.summarize import summarize

CHAT = """\
개발팀님과 카카오톡 대화
저장한 날짜 : 2026-09-07 21:10:00

--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:00] 9월 20일에 출시하는 걸로 하죠
[김서연] [오전 9:05] 배포 문서 정리해주세요
[이민호] [오전 9:10] 제 번호는 010-1234-5678 입니다
[김서연] [오전 9:20] 자료는 https://example.com/doc 에 있습니다
--------------- 2026년 9월 2일 수요일 ---------------
[박지훈] [오전 10:00] 문서 올렸습니다
"""


class SummarizeTest(unittest.TestCase):
    def setUp(self):
        self.summary = summarize(parse_text(CHAT))

    def test_headline(self):
        self.assertIn("3명", self.summary.headline)
        self.assertIn("2026-09-01", self.summary.headline)

    def test_sections_per_day(self):
        self.assertEqual([s.label[:10] for s in self.summary.sections], ["2026-09-01", "2026-09-02"])

    def test_highlights_collected(self):
        self.assertTrue(self.summary.hits["decision"])
        self.assertTrue(self.summary.hits["todo"])
        self.assertTrue(self.summary.hits["link"])

    def test_contact_note_added(self):
        self.assertTrue(any("전화번호" in note for note in self.summary.notes))

    def test_group_none_has_no_sections(self):
        self.assertEqual(summarize(parse_text(CHAT), group="none").sections, [])

    def test_group_session(self):
        summary = summarize(parse_text(CHAT), group="session")
        self.assertEqual(len(summary.sections), 2)

    def test_invalid_group(self):
        with self.assertRaises(ValueError):
            summarize(parse_text(CHAT), group="월간")

    def test_max_items_limits_section_lines(self):
        summary = summarize(parse_text(CHAT), max_items=1)
        for section in summary.sections:
            for items in section.hits.values():
                self.assertLessEqual(len(items), 1)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.summary = summarize(parse_text(CHAT))

    def test_markdown_structure(self):
        text = render_markdown(self.summary)
        self.assertTrue(text.startswith("# 카카오톡 대화 요약 — 개발팀"))
        for heading in ("## 한눈에 보기", "## 참여자", "## 결정된 것", "## 날짜별 정리"):
            self.assertIn(heading, text)

    def test_text_output_has_no_markdown_headings(self):
        text = render_text(self.summary)
        self.assertNotIn("## ", text)
        self.assertIn("[한눈에 보기]", text)

    def test_json_is_valid_and_complete(self):
        data = json.loads(render(self.summary, "json"))
        self.assertEqual(data["stats"]["speech"], 5)
        self.assertIn("sections", data)
        self.assertEqual(len(data["sections"]), 2)

    def test_redact_hides_phone_number(self):
        self.assertNotIn("1234-5678", render_markdown(self.summary, redact=True))
        self.assertNotIn("1234-5678", render(self.summary, "json", redact=True))

    def test_narrative_is_included(self):
        self.summary.narrative = "AI 가 쓴 요약입니다."
        self.summary.narrative_model = "claude-opus-5"
        text = render_markdown(self.summary)
        self.assertIn("## 대화 요약", text)
        self.assertIn("claude-opus-5", text)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            render(self.summary, "pdf")


if __name__ == "__main__":
    unittest.main()
