"""카카오톡 대화 로그를 표현하는 자료 구조."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator, Sequence

# 메시지 종류
KIND_TEXT = "text"        # 일반 텍스트
KIND_MEDIA = "media"      # 사진 / 동영상 / 파일 / 음성메시지
KIND_EMOTICON = "emoticon"  # 이모티콘
KIND_DELETED = "deleted"  # 삭제된 메시지
KIND_SYSTEM = "system"    # 입장 / 퇴장 / 초대 등 시스템 알림

#: 발화로 집계하는 종류 (시스템 알림 제외)
SPEECH_KINDS = frozenset({KIND_TEXT, KIND_MEDIA, KIND_EMOTICON, KIND_DELETED})


@dataclass(frozen=True)
class Message:
    """대화 한 줄."""

    dt: datetime | None
    sender: str
    text: str
    kind: str = KIND_TEXT
    line_no: int = 0

    @property
    def is_speech(self) -> bool:
        """사람이 보낸 메시지인지 (시스템 알림이 아닌지)."""
        return self.kind in SPEECH_KINDS

    @property
    def day(self) -> date | None:
        return self.dt.date() if self.dt else None

    def to_dict(self) -> dict:
        return {
            "datetime": self.dt.isoformat() if self.dt else None,
            "sender": self.sender,
            "text": self.text,
            "kind": self.kind,
            "line_no": self.line_no,
        }


@dataclass
class ChatLog:
    """파싱된 대화 전체."""

    messages: list[Message] = field(default_factory=list)
    title: str | None = None
    saved_at: datetime | None = None
    source_format: str = "unknown"
    source_name: str | None = None
    skipped_lines: int = 0

    def __len__(self) -> int:
        return len(self.messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self.messages)

    @property
    def speech(self) -> list[Message]:
        return [m for m in self.messages if m.is_speech]

    @property
    def participants(self) -> list[str]:
        """등장 순서대로 정리한 참여자 목록."""
        seen: dict[str, None] = {}
        for m in self.messages:
            if m.is_speech and m.sender:
                seen.setdefault(m.sender, None)
        return list(seen)

    @property
    def start(self) -> datetime | None:
        return next((m.dt for m in self.messages if m.dt), None)

    @property
    def end(self) -> datetime | None:
        return next((m.dt for m in reversed(self.messages) if m.dt), None)

    @property
    def days(self) -> list[date]:
        """대화가 오간 날짜 목록 (오름차순, 중복 제거)."""
        seen: dict[date, None] = {}
        for m in self.messages:
            if m.dt:
                seen.setdefault(m.dt.date(), None)
        return sorted(seen)

    def filtered(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        senders: Sequence[str] | None = None,
        include_system: bool = True,
    ) -> "ChatLog":
        """기간 · 발신자 조건으로 걸러낸 새 ChatLog 를 돌려준다."""
        sender_set = {s.strip() for s in senders} if senders else None
        picked: list[Message] = []
        for m in self.messages:
            if since and (m.dt is None or m.dt < since):
                continue
            if until and (m.dt is None or m.dt > until):
                continue
            if not include_system and m.kind == KIND_SYSTEM:
                continue
            if sender_set is not None and m.sender not in sender_set:
                continue
            picked.append(m)
        return ChatLog(
            messages=picked,
            title=self.title,
            saved_at=self.saved_at,
            source_format=self.source_format,
            source_name=self.source_name,
            skipped_lines=self.skipped_lines,
        )

    def last_days(self, days: int) -> "ChatLog":
        """마지막 대화일 기준 최근 N일만 남긴다."""
        end = self.end
        if end is None or days <= 0:
            return self
        since = datetime.combine(end.date() - timedelta(days=days - 1), datetime.min.time())
        return self.filtered(since=since)

    def by_day(self) -> list[tuple[date, list[Message]]]:
        """날짜별로 묶은 (날짜, 메시지들) 목록."""
        buckets: dict[date, list[Message]] = {}
        for m in self.messages:
            if m.dt:
                buckets.setdefault(m.dt.date(), []).append(m)
        return sorted(buckets.items())

    def sessions(self, gap_minutes: int = 180) -> list[list[Message]]:
        """일정 시간 이상 끊긴 지점을 기준으로 대화 덩어리를 나눈다."""
        gap = timedelta(minutes=gap_minutes)
        chunks: list[list[Message]] = []
        current: list[Message] = []
        prev: datetime | None = None
        for m in self.messages:
            if m.dt and prev and m.dt - prev > gap and current:
                chunks.append(current)
                current = []
            current.append(m)
            if m.dt:
                prev = m.dt
        if current:
            chunks.append(current)
        return chunks

    def masked(self, keep: Iterable[str] = ()) -> "ChatLog":
        """참여자 이름을 '참여자 A' 식으로 익명화한 사본을 돌려준다."""
        keep_set = set(keep)
        alias: dict[str, str] = {}
        for i, name in enumerate(self.participants):
            if name in keep_set:
                alias[name] = name
            else:
                alias[name] = f"참여자 {chr(ord('A') + i) if i < 26 else i + 1}"
        renamed = [
            Message(m.dt, alias.get(m.sender, m.sender), m.text, m.kind, m.line_no)
            for m in self.messages
        ]
        return ChatLog(
            messages=renamed,
            title=self.title,
            saved_at=self.saved_at,
            source_format=self.source_format,
            source_name=self.source_name,
            skipped_lines=self.skipped_lines,
        )
