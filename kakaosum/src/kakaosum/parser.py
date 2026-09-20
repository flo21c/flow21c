"""카카오톡에서 내보낸 대화 .txt 파일 파서.

안드로이드 / 아이폰 / PC(윈도우) 내보내기의 서로 다른 줄 형식을 모두 읽는다.

  안드로이드·PC : ``[홍길동] [오후 1:23] 안녕하세요``   (+ 날짜 구분선)
  아이폰·구버전 PC : ``2024년 1월 3일 오후 1:23, 홍길동 : 안녕하세요``

여러 줄 메시지, 시스템 알림(입장·퇴장), 사진/이모티콘/삭제된 메시지도 구분해 준다.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .models import (
    KIND_DELETED,
    KIND_EMOTICON,
    KIND_MEDIA,
    KIND_SYSTEM,
    KIND_TEXT,
    ChatLog,
    Message,
)

# 내보내기 파일에서 실제로 쓰이는 인코딩 후보 (PC 내보내기는 cp949 인 경우가 있다)
ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr", "utf-16")

_TIME = r"(?:오전|오후|AM|PM|am|pm)?\s?\d{1,2}:\d{2}(?:\s?(?:AM|PM|am|pm))?"

# [홍길동] [오후 1:23] 메시지
BRACKET_RE = re.compile(rf"^\[(?P<sender>.+?)\]\s\[(?P<time>{_TIME})\]\s?(?P<text>.*)$")

# 2024년 1월 3일 오후 1:23, 홍길동 : 메시지   /   2024. 1. 3. 오후 1:23, 홍길동 : 메시지
INLINE_RE = re.compile(
    r"^(?P<y>\d{4})\s*[.년]\s*(?P<mo>\d{1,2})\s*[.월]\s*(?P<d>\d{1,2})\s*[.일]?\s+"
    rf"(?P<time>{_TIME})\s*[,:]?\s+(?P<rest>.*)$"
)

# --------------- 2024년 1월 3일 수요일 ---------------
SEPARATOR_RE = re.compile(r"^-{3,}\s*(?P<body>.+?)\s*-{3,}$")
KO_DATE_RE = re.compile(r"(?P<y>\d{4})\s*[.년]\s*(?P<mo>\d{1,2})\s*[.월]\s*(?P<d>\d{1,2})\s*일?")
EN_DATE_RE = re.compile(
    r"(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<d>\d{1,2}),?\s+(?P<y>\d{4})",
    re.IGNORECASE,
)
_EN_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        "January February March April May June July August September October November December".split(),
        start=1,
    )
}

HEADER_TITLE_RE = re.compile(r"^(?P<title>.*?)\s*(?:님과(?:의)?\s*)?카카오톡\s*대화$")
SAVED_AT_RE = re.compile(r"^저장한\s*날짜\s*:\s*(?P<value>.+?)\s*$")

# 시스템 알림 (발신자 없이 한 줄로 들어온다)
SYSTEM_PATTERNS = (
    re.compile(r"님이 (들어왔|나갔|퇴장하였)습니다\.?$"),
    re.compile(r"님을 (내보냈|초대했|초대하였)습니다\.?$"),
    re.compile(r"님이 .*(방장|관리자).*(되었|됐)습니다\.?$"),
    re.compile(r"^(채팅방|그룹채팅방|오픈채팅방).*(개설|변경|생성)"),
    re.compile(r"운영정책"),
    re.compile(r"(공지|투표)(가|를) (등록|시작|종료)"),
    re.compile(r"^(저장한 날짜|카카오톡 대화)"),
)

MEDIA_PATTERNS = (
    re.compile(r"^사진(\s*\d+장)?$"),
    re.compile(r"^동영상$"),
    re.compile(r"^음성메시지$"),
    re.compile(r"^(파일|첨부파일)\s*:"),
    re.compile(r"^<?(사진|동영상|파일|보이스톡|페이스톡|라이브톡)[^>]*>?$"),
    re.compile(r"^(보이스톡|페이스톡|라이브톡)\s*(해요|종료|취소)?$"),
    re.compile(r"^지도:"),
    re.compile(r"^샵검색:"),
)
EMOTICON_PATTERNS = (
    re.compile(r"^\(?이모티콘\)?$"),
    re.compile(r"^이모티콘을 보냈습니다\.?$"),
)
DELETED_PATTERNS = (
    re.compile(r"^삭제된 메시지입니다\.?$"),
    re.compile(r"^(가려진|차단된) 메시지입니다\.?$"),
)


class ParseError(ValueError):
    """대화 파일로 보이지 않을 때."""


def read_text(path: str | Path) -> str:
    """인코딩을 추정해 파일 내용을 읽는다."""
    raw = Path(path).read_bytes()
    last: UnicodeDecodeError | None = None
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError as exc:  # pragma: no cover - 인코딩별 분기
            last = exc
    raise ParseError(f"파일 인코딩을 알 수 없습니다: {path}") from last


def parse_file(path: str | Path) -> ChatLog:
    """대화 .txt 파일을 읽어 ChatLog 로 만든다."""
    log = parse_text(read_text(path))
    log.source_name = Path(path).name
    return log


def parse_text(text: str) -> ChatLog:
    """문자열로 들어온 대화 내용을 ChatLog 로 만든다."""
    return _Parser(text.splitlines()).run()


def _classify(text: str) -> str:
    stripped = text.strip()
    for pat in DELETED_PATTERNS:
        if pat.match(stripped):
            return KIND_DELETED
    for pat in EMOTICON_PATTERNS:
        if pat.match(stripped):
            return KIND_EMOTICON
    for pat in MEDIA_PATTERNS:
        if pat.match(stripped):
            return KIND_MEDIA
    return KIND_TEXT


def _looks_system(text: str) -> bool:
    stripped = text.strip()
    return any(pat.search(stripped) for pat in SYSTEM_PATTERNS)


def _parse_clock(value: str) -> tuple[int, int]:
    """'오후 1:23' / '1:23 PM' / '13:23' → (13, 23)."""
    v = value.strip()
    pm = "오후" in v or re.search(r"\b[Pp][Mm]\b", v) is not None
    am = "오전" in v or re.search(r"\b[Aa][Mm]\b", v) is not None
    nums = re.search(r"(\d{1,2}):(\d{2})", v)
    if not nums:
        raise ValueError(f"시각을 읽을 수 없습니다: {value!r}")
    hour, minute = int(nums.group(1)), int(nums.group(2))
    if pm and hour < 12:
        hour += 12
    elif am and hour == 12:
        hour = 0
    return hour % 24, minute


def _parse_date_line(body: str) -> date | None:
    m = KO_DATE_RE.search(body)
    if m:
        return date(int(m.group("y")), int(m.group("mo")), int(m.group("d")))
    m = EN_DATE_RE.search(body)
    if m:
        return date(int(m.group("y")), _EN_MONTHS[m.group("mon").lower()], int(m.group("d")))
    return None


def _parse_saved_at(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y년 %m월 %d일 %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    m = KO_DATE_RE.search(value)
    if m:
        return datetime(int(m.group("y")), int(m.group("mo")), int(m.group("d")))
    return None


class _Parser:
    def __init__(self, lines: Iterable[str]) -> None:
        self.lines = list(lines)
        self.log = ChatLog()
        self.current_date: date | None = None
        self.last_dt: datetime | None = None
        self.buffer: list[str] = []      # 이어지는 줄을 모아 둘 곳
        self.pending: Message | None = None
        self.blank_run = 0
        self.bracket_hits = 0
        self.inline_hits = 0

    # -- 조립 ---------------------------------------------------------------
    def _flush(self) -> None:
        if self.pending is None:
            return
        text = self.pending.text
        if self.buffer:
            text = "\n".join([text, *self.buffer]).strip("\n")
        kind = self.pending.kind
        if kind != KIND_SYSTEM and self.buffer:
            kind = KIND_TEXT  # 여러 줄이면 사진/이모티콘 한 줄짜리가 아니다
        self.log.messages.append(
            Message(self.pending.dt, self.pending.sender, text, kind, self.pending.line_no)
        )
        self.pending = None
        self.buffer = []
        self.blank_run = 0

    def _push(self, message: Message) -> None:
        self._flush()
        self.pending = message

    # -- 본체 ---------------------------------------------------------------
    def run(self) -> ChatLog:
        for idx, raw in enumerate(self.lines, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                if self.pending is not None:
                    self.blank_run += 1
                continue
            if self._handle(line, idx):
                continue
            self._continuation(line)

        self._flush()
        self.log.source_format = (
            "bracket" if self.bracket_hits >= self.inline_hits and self.bracket_hits else
            "inline" if self.inline_hits else "unknown"
        )
        if not self.log.messages:
            raise ParseError(
                "카카오톡 대화 내용을 찾지 못했습니다. "
                "카카오톡에서 '대화 내보내기 → 텍스트만 보내기'로 저장한 .txt 파일인지 확인해 주세요."
            )
        return self.log

    def _handle(self, line: str, idx: int) -> bool:
        """머리말 · 날짜 구분선 · 메시지 줄이면 처리하고 True."""
        sep = SEPARATOR_RE.match(line)
        if sep:
            found = _parse_date_line(sep.group("body"))
            if found:
                self._flush()
                self.current_date = found
                return True

        if self._maybe_header(line):
            return True

        # 날짜만 있는 구분 줄 (구버전 안드로이드)
        if re.fullmatch(r"\d{4}\s*[.년]\s*\d{1,2}\s*[.월]\s*\d{1,2}\s*일?\s*[월화수목금토일]?요?일?", line.strip()):
            found = _parse_date_line(line)
            if found:
                self._flush()
                self.current_date = found
                return True

        m = BRACKET_RE.match(line)
        if m:
            self.bracket_hits += 1
            try:
                hour, minute = _parse_clock(m.group("time"))
            except ValueError:  # pragma: no cover - 시각이 깨진 줄
                return False
            dt = (
                datetime.combine(self.current_date, datetime.min.time()).replace(hour=hour, minute=minute)
                if self.current_date
                else None
            )
            text = m.group("text")
            if dt:
                self.last_dt = dt
            self._push(Message(dt, m.group("sender").strip(), text, _classify(text), idx))
            return True

        m = INLINE_RE.match(line)
        if m:
            self.inline_hits += 1
            try:
                hour, minute = _parse_clock(m.group("time"))
            except ValueError:  # pragma: no cover
                return False
            dt = datetime(int(m.group("y")), int(m.group("mo")), int(m.group("d")), hour, minute)
            self.current_date = dt.date()
            self.last_dt = dt
            rest = m.group("rest")
            sender, sep_found, text = rest.partition(" : ")
            if sep_found:
                self._push(Message(dt, sender.strip(), text, _classify(text), idx))
            else:
                self._push(Message(dt, "", rest.strip(), KIND_SYSTEM, idx))
            return True

        if _looks_system(line):
            # 시스템 알림에는 시각이 없다. 직전 메시지 시각을 물려줘 순서를 지킨다.
            dt = self.last_dt
            if dt is None or (self.current_date and dt.date() != self.current_date):
                dt = (
                    datetime.combine(self.current_date, datetime.min.time())
                    if self.current_date
                    else None
                )
            self._push(Message(dt, "", line.strip(), KIND_SYSTEM, idx))
            return True

        return False

    def _maybe_header(self, line: str) -> bool:
        """파일 맨 앞의 제목 / 저장 날짜 줄."""
        if self.log.messages or self.pending is not None:
            return False
        saved = SAVED_AT_RE.match(line.strip())
        if saved:
            self.log.saved_at = _parse_saved_at(saved.group("value"))
            return True
        head = HEADER_TITLE_RE.match(line.strip())
        if head:
            title = head.group("title").strip()
            self.log.title = title or None
            return True
        return False

    def _continuation(self, line: str) -> None:
        """앞 메시지의 이어지는 줄."""
        if self.pending is None:
            self.log.skipped_lines += 1
            return
        if self.blank_run:
            self.buffer.extend([""] * self.blank_run)
            self.blank_run = 0
        self.buffer.append(line)


def parse_stream(stream: io.TextIOBase) -> ChatLog:
    """열린 텍스트 스트림(예: 표준 입력)에서 읽는다."""
    return parse_text(stream.read())
