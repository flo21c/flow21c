"""분석 결과를 사람이 읽는 요약 구조로 조립한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .analyze import (
    CATEGORY_LABELS,
    Hit,
    Keyword,
    Stats,
    compute_stats,
    find_hits,
    group_hits,
    has_contact_info,
    keywords,
)
from .models import KIND_SYSTEM, ChatLog, Message

GROUP_DAY = "day"
GROUP_SESSION = "session"
GROUP_NONE = "none"
GROUPS = (GROUP_DAY, GROUP_SESSION, GROUP_NONE)


@dataclass
class Section:
    """날짜 또는 대화 덩어리 하나에 대한 요약."""

    label: str
    start: datetime | None
    end: datetime | None
    message_count: int
    speakers: list[tuple[str, int]]
    keywords: list[Keyword]
    hits: dict[str, list[Hit]]

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "message_count": self.message_count,
            "speakers": [{"name": n, "messages": c} for n, c in self.speakers],
            "keywords": [k.to_dict() for k in self.keywords],
            "highlights": {
                key: [h.to_dict() for h in items] for key, items in self.hits.items() if items
            },
        }


@dataclass
class Summary:
    """요약 전체. render 모듈이 이 구조를 글로 바꾼다."""

    title: str | None
    source_name: str | None
    generated_at: datetime
    stats: Stats
    keywords: list[Keyword]
    sections: list[Section]
    hits: dict[str, list[Hit]]
    group: str = GROUP_DAY
    narrative: str | None = None          # AI 요약 (옵션)
    narrative_model: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def headline(self) -> str:
        """한 줄 개요."""
        stats = self.stats
        people = len(stats.participants)
        if stats.start and stats.end:
            span = f"{stats.start:%Y-%m-%d} ~ {stats.end:%Y-%m-%d}"
        else:
            span = "기간 정보 없음"
        return (
            f"{span} 사이 {people}명이 나눈 대화 {stats.speech:,}건"
            f" (대화가 오간 날 {stats.active_days}일)"
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source_name,
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "headline": self.headline,
            "group": self.group,
            "stats": self.stats.to_dict(),
            "keywords": [k.to_dict() for k in self.keywords],
            "highlights": {
                key: [h.to_dict() for h in items] for key, items in self.hits.items() if items
            },
            "sections": [s.to_dict() for s in self.sections],
            "narrative": self.narrative,
            "narrative_model": self.narrative_model,
            "notes": self.notes,
        }


def _speaker_counts(messages: list[Message], top: int = 5) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for m in messages:
        if m.kind != KIND_SYSTEM and m.sender:
            counts[m.sender] = counts.get(m.sender, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def _bounds(messages: list[Message]) -> tuple[datetime | None, datetime | None]:
    stamps = [m.dt for m in messages if m.dt]
    return (stamps[0], stamps[-1]) if stamps else (None, None)


def _day_label(day: date) -> str:
    weekday = "월화수목금토일"[day.weekday()]
    return f"{day:%Y-%m-%d} ({weekday})"


def _limit(grouped: dict[str, list[Hit]], max_items: int) -> dict[str, list[Hit]]:
    return {key: items[:max_items] for key, items in grouped.items()}


def _build_sections(
    log: ChatLog,
    *,
    group: str,
    top_keywords: int,
    max_items: int,
    answer_window_minutes: int,
) -> list[Section]:
    if group == GROUP_NONE:
        return []

    if group == GROUP_DAY:
        chunks: list[tuple[str, list[Message]]] = [
            (_day_label(day), msgs) for day, msgs in log.by_day()
        ]
    else:
        chunks = []
        for msgs in log.sessions():
            start, end = _bounds(msgs)
            if start and end:
                label = f"{start:%Y-%m-%d %H:%M} ~ {end:%H:%M}"
            else:
                label = "시간 정보 없음"
            chunks.append((label, msgs))

    sections: list[Section] = []
    for label, msgs in chunks:
        part = ChatLog(messages=msgs)
        start, end = _bounds(msgs)
        sections.append(
            Section(
                label=label,
                start=start,
                end=end,
                message_count=sum(1 for m in msgs if m.kind != KIND_SYSTEM),
                speakers=_speaker_counts(msgs),
                keywords=keywords(msgs, top_n=min(top_keywords, 8), min_count=2),
                hits=_limit(
                    group_hits(find_hits(part, answer_window_minutes=answer_window_minutes)),
                    max_items,
                ),
            )
        )
    return sections


def summarize(
    log: ChatLog,
    *,
    group: str = GROUP_DAY,
    top_keywords: int = 15,
    max_items: int = 8,
    answer_window_minutes: int = 120,
) -> Summary:
    """ChatLog → Summary."""
    if group not in GROUPS:
        raise ValueError(f"group 은 {GROUPS} 중 하나여야 합니다: {group!r}")

    stats = compute_stats(log)
    all_hits = group_hits(find_hits(log, answer_window_minutes=answer_window_minutes))

    notes: list[str] = []
    if log.skipped_lines:
        notes.append(f"형식을 알 수 없어 건너뛴 줄 {log.skipped_lines:,}개가 있습니다.")
    if stats.speech and not stats.start:
        notes.append("날짜 구분선이 없어 시간 정보 없이 요약했습니다.")
    if has_contact_info(log):
        notes.append("전화번호나 이메일이 포함돼 있습니다. 공유 전에 확인하세요. (--redact 로 가릴 수 있습니다)")

    return Summary(
        title=log.title,
        source_name=log.source_name,
        generated_at=datetime.now(),
        stats=stats,
        keywords=keywords(log.messages, top_n=top_keywords),
        sections=_build_sections(
            log,
            group=group,
            top_keywords=top_keywords,
            max_items=max_items,
            answer_window_minutes=answer_window_minutes,
        ),
        hits=_limit(all_hits, max_items * 3),
        group=group,
        notes=notes,
    )


__all__ = [
    "CATEGORY_LABELS",
    "GROUPS",
    "GROUP_DAY",
    "GROUP_NONE",
    "GROUP_SESSION",
    "Section",
    "Summary",
    "summarize",
]
