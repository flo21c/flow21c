import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from kakaosum.cli import main

CHAT = """\
개발팀님과 카카오톡 대화
저장한 날짜 : 2026-09-07 21:10:00

--------------- 2026년 9월 1일 화요일 ---------------
[박지훈] [오전 9:00] 9월 20일에 출시하는 걸로 하죠
[김서연] [오전 9:05] 배포 문서 정리해주세요. 제 번호는 010-1234-5678 입니다
--------------- 2026년 9월 5일 토요일 ---------------
[박지훈] [오전 10:00] 문서 올렸습니다
"""


def run(args, stdin: str | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    original = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
    finally:
        sys.stdin = original
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "chat.txt"
        self.path.write_text(CHAT, encoding="utf-8")

    def test_summarize_to_stdout(self):
        code, out, _ = run(["summarize", str(self.path)])
        self.assertEqual(code, 0)
        self.assertIn("# 카카오톡 대화 요약", out)

    def test_summarize_to_file(self):
        target = Path(self.tmp.name) / "summary.md"
        code, out, err = run(["summarize", str(self.path), "-o", str(target)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("저장했습니다", err)
        self.assertIn("결정된 것", target.read_text(encoding="utf-8"))

    def test_json_format(self):
        _, out, _ = run(["summarize", str(self.path), "-f", "json"])
        self.assertEqual(json.loads(out)["stats"]["speech"], 3)

    def test_stdin_input(self):
        _, out, _ = run(["summarize", "-", "-f", "json"], stdin=CHAT)
        self.assertEqual(json.loads(out)["source"], "표준 입력")

    def test_last_days_filter(self):
        _, out, _ = run(["summarize", str(self.path), "-f", "json", "--last-days", "1"])
        self.assertEqual(json.loads(out)["stats"]["speech"], 1)

    def test_since_until_filter(self):
        _, out, _ = run(
            ["summarize", str(self.path), "-f", "json", "--since", "2026-09-01",
             "--until", "2026-09-01"]
        )
        self.assertEqual(json.loads(out)["stats"]["speech"], 2)

    def test_sender_filter(self):
        _, out, _ = run(["summarize", str(self.path), "-f", "json", "--sender", "박지훈"])
        names = [p["name"] for p in json.loads(out)["stats"]["participants"]]
        self.assertEqual(names, ["박지훈"])

    def test_mask_and_redact(self):
        _, out, _ = run(["summarize", str(self.path), "--mask", "--redact"])
        self.assertIn("참여자 A", out)
        self.assertNotIn("박지훈", out)
        self.assertNotIn("1234-5678", out)

    def test_stats_command(self):
        _, out, _ = run(["stats", str(self.path), "-f", "json"])
        self.assertEqual(json.loads(out)["active_days"], 2)

    def test_export_csv(self):
        target = Path(self.tmp.name) / "chat.csv"
        run(["export", str(self.path), "-f", "csv", "-o", str(target)])
        lines = target.read_text(encoding="utf-8-sig").splitlines()
        self.assertTrue(lines[0].startswith("datetime,sender,kind,text"))
        self.assertEqual(len(lines), 4)

    def test_export_jsonl(self):
        _, out, _ = run(["export", str(self.path), "-f", "jsonl"])
        rows = [json.loads(line) for line in out.splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sender"], "박지훈")

    def test_missing_file(self):
        with self.assertRaises(SystemExit):
            run(["summarize", str(Path(self.tmp.name) / "없는파일.txt")])

    def test_empty_filter_result(self):
        with self.assertRaises(SystemExit):
            run(["summarize", str(self.path), "--sender", "아무도아님"])

    def test_bad_date_option(self):
        with self.assertRaises(SystemExit):
            run(["summarize", str(self.path), "--since", "9월 1일"])

    def test_unparseable_file_returns_code_2(self):
        junk = Path(self.tmp.name) / "junk.txt"
        junk.write_text("그냥 메모입니다\n", encoding="utf-8")
        code, _, err = run(["summarize", str(junk)])
        self.assertEqual(code, 2)
        self.assertIn("대화 내보내기", err)

    def test_ai_without_confirmation_is_skipped(self):
        # 표준 입력이 터미널이 아니면 물어볼 수 없으므로 AI 요약을 건너뛴다
        _, out, err = run(["summarize", str(self.path), "--ai"], stdin="")
        self.assertIn("AI 요약을 건너뜁니다", err)
        self.assertIn("# 카카오톡 대화 요약", out)


if __name__ == "__main__":
    unittest.main()
