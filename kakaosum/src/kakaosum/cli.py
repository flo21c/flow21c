"""kakaosum 명령줄 도구."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, time
from pathlib import Path

from . import __version__
from .analyze import redact as redact_text
from .models import ChatLog
from .parser import ParseError, parse_file, parse_text
from .render import FORMATS, render
from .summarize import GROUPS, summarize

EXAMPLES = """\
예시:
  kakaosum summarize 대화.txt                     # 화면에 요약 출력
  kakaosum summarize 대화.txt -o 요약.md          # 파일로 저장
  kakaosum summarize 대화.txt --last-days 7       # 최근 7일만
  kakaosum summarize 대화.txt --group session     # 날짜 대신 대화 덩어리로 묶기
  kakaosum summarize 대화.txt --mask --redact     # 이름·연락처 가리기
  kakaosum summarize 대화.txt --ai                # Claude 자연어 요약 덧붙이기
  kakaosum stats 대화.txt                         # 통계만 보기
  kakaosum export 대화.txt -f csv -o 대화.csv     # 파싱 결과 내보내기
"""


def _parse_day(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"날짜 형식이 올바르지 않습니다: {value} (예: 2026-09-01)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kakaosum",
        description="카카오톡에서 내보낸 대화 .txt 를 읽어 정리·요약합니다.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"kakaosum {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("file", help="대화 .txt 파일 경로 ('-' 이면 표준 입력)")
        p.add_argument("-o", "--output", help="결과를 저장할 파일 (기본: 화면 출력)")
        p.add_argument("--since", type=_parse_day, metavar="YYYY-MM-DD", help="이 날짜부터")
        p.add_argument("--until", type=_parse_day, metavar="YYYY-MM-DD", help="이 날짜까지")
        p.add_argument("--last-days", type=int, metavar="N", help="마지막 대화일 기준 최근 N일")
        p.add_argument(
            "--sender", action="append", metavar="이름", help="이 사람 메시지만 (여러 번 지정 가능)"
        )
        p.add_argument("--no-system", action="store_true", help="입·퇴장 알림 제외")
        p.add_argument("--mask", action="store_true", help="참여자 이름을 '참여자 A' 로 익명화")
        p.add_argument("--redact", action="store_true", help="전화번호·이메일 가리기")

    p_sum = sub.add_parser("summarize", help="대화를 정리해 요약합니다", description="대화를 정리해 요약합니다.")
    add_common(p_sum)
    p_sum.add_argument("-f", "--format", choices=FORMATS, default="markdown", help="출력 형식")
    p_sum.add_argument("--group", choices=GROUPS, default="day", help="구간을 나누는 기준")
    p_sum.add_argument("--top-keywords", type=int, default=15, metavar="N", help="키워드 개수")
    p_sum.add_argument("--max-items", type=int, default=8, metavar="N", help="항목별 최대 줄 수")
    p_sum.add_argument(
        "--answer-window",
        type=int,
        default=120,
        metavar="분",
        help="이 시간 안에 답이 없으면 '답 없는 질문'으로 봅니다 (기본 120분)",
    )
    p_sum.add_argument("--ai", action="store_true", help="Claude 로 자연어 요약을 덧붙입니다")
    p_sum.add_argument("--ai-model", default=None, metavar="모델", help="사용할 Claude 모델")
    p_sum.add_argument(
        "--ai-chunk-chars", type=int, default=None, metavar="N", help="한 번에 보낼 글자 수"
    )
    p_sum.add_argument("-y", "--yes", action="store_true", help="AI 전송 확인 묻지 않기")

    p_stats = sub.add_parser("stats", help="통계만 봅니다", description="대화 통계만 봅니다.")
    add_common(p_stats)
    p_stats.add_argument("-f", "--format", choices=("text", "json"), default="text")

    p_export = sub.add_parser(
        "export", help="파싱 결과를 CSV/JSONL 로 내보냅니다", description="파싱한 메시지를 내보냅니다."
    )
    add_common(p_export)
    p_export.add_argument("-f", "--format", choices=("csv", "jsonl"), default="csv")

    return parser


def load_log(args: argparse.Namespace) -> ChatLog:
    if args.file == "-":
        log = parse_text(sys.stdin.read())
        log.source_name = "표준 입력"
    else:
        path = Path(args.file)
        if not path.exists():
            raise SystemExit(f"파일을 찾을 수 없습니다: {path}")
        log = parse_file(path)

    log = log.filtered(
        since=args.since,
        until=datetime.combine(args.until.date(), time.max) if args.until else None,
        senders=args.sender,
        include_system=not args.no_system,
    )
    if args.last_days:
        log = log.last_days(args.last_days)
    if args.mask:
        log = log.masked()
    if not log.messages:
        raise SystemExit("조건에 맞는 메시지가 없습니다. 기간이나 --sender 를 확인해 주세요.")
    return log


def _write(text: str, output: str | None, *, bom: bool = False) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8-sig" if bom else "utf-8")
        print(f"저장했습니다: {output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


def _confirm_ai(log: ChatLog, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    chars = sum(len(m.text) for m in log.messages)
    print(
        f"AI 요약을 쓰면 대화 {len(log.messages):,}건({chars:,}자)이 Anthropic API 로 전송됩니다.",
        file=sys.stderr,
    )
    if not sys.stdin.isatty():
        print("확인할 수 없어 AI 요약을 건너뜁니다. (--yes 로 생략 가능)", file=sys.stderr)
        return False
    answer = input("계속할까요? [y/N] ").strip().lower()
    return answer in ("y", "yes", "ㅇ")


def cmd_summarize(args: argparse.Namespace) -> int:
    log = load_log(args)
    summary = summarize(
        log,
        group=args.group,
        top_keywords=args.top_keywords,
        max_items=args.max_items,
        answer_window_minutes=args.answer_window,
    )

    if args.ai:
        from .ai import DEFAULT_CHUNK_CHARS, DEFAULT_MODEL, AIError, summarize_with_claude

        if _confirm_ai(log, args.yes):
            try:
                result = summarize_with_claude(
                    log,
                    model=args.ai_model or DEFAULT_MODEL,
                    chunk_chars=args.ai_chunk_chars or DEFAULT_CHUNK_CHARS,
                    redact=args.redact,
                )
            except AIError as exc:
                print(f"AI 요약을 건너뜁니다: {exc}", file=sys.stderr)
            else:
                summary.narrative = result.text
                summary.narrative_model = result.model
                if result.chunks > 1:
                    summary.notes.append(
                        f"대화가 길어 {result.chunks}개로 나눠 요약한 뒤 합쳤습니다."
                    )

    _write(render(summary, args.format, redact=args.redact), args.output)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    log = load_log(args)
    if args.format == "json":
        from .analyze import compute_stats

        _write(
            json.dumps(compute_stats(log).to_dict(), ensure_ascii=False, indent=2) + "\n",
            args.output,
        )
        return 0

    summary = summarize(log, group="none", top_keywords=15)
    _write(render(summary, "text", redact=args.redact), args.output)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    log = load_log(args)
    rows = []
    for m in log.messages:
        row = m.to_dict()
        if args.redact:
            row["text"] = redact_text(row["text"])
            row["sender"] = redact_text(row["sender"])
        rows.append(row)

    if args.format == "jsonl":
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        _write(text, args.output)
        return 0

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["datetime", "sender", "kind", "text", "line_no"])
    writer.writeheader()
    writer.writerows(rows)
    _write(buffer.getvalue(), args.output, bom=True)
    return 0


COMMANDS = {"summarize": cmd_summarize, "stats": cmd_stats, "export": cmd_export}

BANNER = """\
kakaosum — 카카오톡 대화 요약기
카카오톡에서 '대화 내용 내보내기 → 텍스트만 보내기' 로 저장한 .txt 파일을 넣어 주세요.
(파일을 이 창에 끌어다 놓아도 됩니다. 그냥 끝내려면 Enter)
"""


def interactive() -> int:
    """인자 없이 실행했을 때(예: exe 더블클릭) 물어 가며 요약한다."""
    print(BANNER)
    answer = input("대화 파일 경로: ").strip().strip('"').strip("'")
    if not answer:
        return 0

    path = Path(answer)
    if not path.exists():
        print(f"파일을 찾을 수 없습니다: {path}")
        input("Enter 를 누르면 닫힙니다...")
        return 1

    try:
        log = parse_file(path)
        summary = summarize(log)
        text = render(summary, "markdown")
    except ParseError as exc:
        print(f"오류: {exc}")
        input("Enter 를 누르면 닫힙니다...")
        return 2

    target = path.with_name(f"{path.stem}_요약.md")
    target.write_text(text, encoding="utf-8")
    print()
    print(summary.headline)
    print(f"요약을 저장했습니다: {target}")
    input("Enter 를 누르면 닫힙니다...")
    return 0


def _normalize_argv(args: list[str]) -> list[str]:
    """파일을 exe 에 끌어다 놓으면 'summarize 파일' 로 바꿔 준다."""
    if args and args[0] not in COMMANDS and not args[0].startswith("-") and Path(args[0]).exists():
        return ["summarize", *args]
    return args


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # 윈도우 콘솔에서 한글이 깨지지 않도록
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw and sys.stdin.isatty():
        return interactive()

    args = build_parser().parse_args(_normalize_argv(raw))
    try:
        return COMMANDS[args.command](args)
    except ParseError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("중단했습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
