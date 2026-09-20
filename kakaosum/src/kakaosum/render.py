"""Summary 를 마크다운 · 텍스트 · JSON 으로 옮긴다."""

from __future__ import annotations

import json
from datetime import datetime

from .analyze import CATEGORY_LABELS, Hit, redact as redact_text
from .summarize import GROUP_NONE, Summary

FORMATS = ("markdown", "text", "json")

CATEGORY_ORDER = ("decision", "todo", "schedule", "question", "link", "money")


def _stamp(dt: datetime | None) -> str:
    return f"{dt:%m-%d %H:%M}" if dt else "시각 미상"


def _hit_line(hit: Hit, *, redact: bool) -> str:
    who = hit.message.sender or "시스템"
    snippet = redact_text(hit.snippet) if redact else hit.snippet
    return f"[{_stamp(hit.message.dt)}] {who}: {snippet}"


def _bar(value: int, top: int, width: int = 20) -> str:
    if top <= 0:
        return ""
    filled = max(1, round(value / top * width)) if value else 0
    return "█" * filled


def render(summary: Summary, fmt: str = "markdown", *, redact: bool = False) -> str:
    if fmt == "json":
        return render_json(summary, redact=redact)
    if fmt == "text":
        return render_text(summary, redact=redact)
    if fmt == "markdown":
        return render_markdown(summary, redact=redact)
    raise ValueError(f"지원하지 않는 형식입니다: {fmt!r} (가능: {', '.join(FORMATS)})")


def render_json(summary: Summary, *, redact: bool = False) -> str:
    data = summary.to_dict()
    if redact:
        data = json.loads(redact_text(json.dumps(data, ensure_ascii=False)))
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_markdown(summary: Summary, *, redact: bool = False) -> str:
    stats = summary.stats
    out: list[str] = []
    title = summary.title or summary.source_name or "카카오톡 대화"
    out.append(f"# 카카오톡 대화 요약 — {title}")
    out.append("")
    out.append(f"> {summary.headline}")
    out.append("")

    if summary.narrative:
        out.append("## 대화 요약")
        out.append("")
        out.append(summary.narrative.strip())
        out.append("")
        if summary.narrative_model:
            out.append(f"<sub>위 요약은 {summary.narrative_model} 모델이 작성했습니다.</sub>")
            out.append("")

    out.append("## 한눈에 보기")
    out.append("")
    out.extend(f"- {line}" for line in _overview_lines(summary))
    out.append("")

    if stats.participants:
        out.append("## 참여자")
        out.append("")
        out.append("| 이름 | 메시지 | 비중 | 글자 수 | 사진·파일 | 질문 | 마지막 발언 |")
        out.append("|---|---:|---:|---:|---:|---:|---|")
        for p in stats.participants:
            name = redact_text(p.name) if redact else p.name
            out.append(
                f"| {name} | {p.messages:,} | {p.share * 100:.1f}% | {p.chars:,} | "
                f"{p.media:,} | {p.questions:,} | {_stamp(p.last)} |"
            )
        out.append("")

    if summary.keywords:
        out.append("## 자주 나온 말")
        out.append("")
        out.append(
            " · ".join(f"**{k.word}**({k.count})" for k in summary.keywords)
        )
        out.append("")

    for key in CATEGORY_ORDER:
        items = summary.hits.get(key) or []
        if not items:
            continue
        out.append(f"## {CATEGORY_LABELS[key]}")
        out.append("")
        out.extend(f"- {_hit_line(h, redact=redact)}" for h in items)
        out.append("")

    if summary.group != GROUP_NONE and summary.sections:
        out.append("## 날짜별 정리" if summary.group == "day" else "## 대화 덩어리별 정리")
        out.append("")
        for section in summary.sections:
            out.append(f"### {section.label} · 메시지 {section.message_count:,}건")
            out.append("")
            if section.speakers:
                who = ", ".join(
                    f"{redact_text(n) if redact else n} {c}" for n, c in section.speakers
                )
                out.append(f"- 발언: {who}")
            if section.keywords:
                out.append("- 주요 낱말: " + ", ".join(k.word for k in section.keywords))
            for key in CATEGORY_ORDER:
                items = section.hits.get(key) or []
                if not items:
                    continue
                out.append(f"- {CATEGORY_LABELS[key]}:")
                out.extend(f"  - {_hit_line(h, redact=redact)}" for h in items)
            out.append("")

    hourly = _hour_chart(summary)
    if hourly:
        out.append("## 시간대별 대화량")
        out.append("")
        out.append("```")
        out.extend(hourly)
        out.append("```")
        out.append("")

    if summary.notes:
        out.append("## 참고")
        out.append("")
        out.extend(f"- {note}" for note in summary.notes)
        out.append("")

    out.append(
        f"<sub>{summary.generated_at:%Y-%m-%d %H:%M} · kakaosum 으로 만들었습니다.</sub>"
    )
    return "\n".join(out).rstrip() + "\n"


def render_text(summary: Summary, *, redact: bool = False) -> str:
    stats = summary.stats
    out: list[str] = []
    title = summary.title or summary.source_name or "카카오톡 대화"
    head = f"카카오톡 대화 요약 — {title}"
    out.append(head)
    out.append("=" * 60)
    out.append(summary.headline)
    out.append("")

    if summary.narrative:
        out.append("[대화 요약]")
        out.append(summary.narrative.strip())
        out.append("")

    out.append("[한눈에 보기]")
    out.extend(f"  - {line}" for line in _overview_lines(summary))
    out.append("")

    if stats.participants:
        out.append("[참여자]")
        for p in stats.participants:
            name = redact_text(p.name) if redact else p.name
            out.append(
                f"  - {name}: {p.messages:,}건 ({p.share * 100:.1f}%), "
                f"{p.chars:,}자, 사진·파일 {p.media:,}건, 질문 {p.questions:,}건"
            )
        out.append("")

    if summary.keywords:
        out.append("[자주 나온 말]")
        out.append("  " + ", ".join(f"{k.word}({k.count})" for k in summary.keywords))
        out.append("")

    for key in CATEGORY_ORDER:
        items = summary.hits.get(key) or []
        if not items:
            continue
        out.append(f"[{CATEGORY_LABELS[key]}]")
        out.extend(f"  - {_hit_line(h, redact=redact)}" for h in items)
        out.append("")

    if summary.group != GROUP_NONE and summary.sections:
        out.append("[날짜별 정리]" if summary.group == "day" else "[대화 덩어리별 정리]")
        for section in summary.sections:
            out.append(f"  {section.label} · 메시지 {section.message_count:,}건")
            if section.keywords:
                out.append("    주요 낱말: " + ", ".join(k.word for k in section.keywords))
            for key in CATEGORY_ORDER:
                items = section.hits.get(key) or []
                for hit in items:
                    out.append(f"    [{CATEGORY_LABELS[key]}] {_hit_line(hit, redact=redact)}")
        out.append("")

    hourly = _hour_chart(summary)
    if hourly:
        out.append("[시간대별 대화량]")
        out.extend(f"  {line}" for line in hourly)
        out.append("")

    if summary.notes:
        out.append("[참고]")
        out.extend(f"  - {note}" for note in summary.notes)
        out.append("")

    out.append(f"{summary.generated_at:%Y-%m-%d %H:%M} · kakaosum")
    return "\n".join(out).rstrip() + "\n"


def _overview_lines(summary: Summary) -> list[str]:
    stats = summary.stats
    lines: list[str] = []
    if stats.start and stats.end:
        lines.append(
            f"기간: {stats.start:%Y-%m-%d %H:%M} ~ {stats.end:%Y-%m-%d %H:%M}"
            f" ({stats.span_days}일 중 {stats.active_days}일 대화)"
        )
    lines.append(
        f"메시지: {stats.speech:,}건 · 하루 평균 {stats.messages_per_active_day:.1f}건"
        f" · 글자 수 {stats.chars:,}자"
    )
    lines.append(f"참여자: {len(stats.participants)}명")
    extras = []
    if stats.media:
        extras.append(f"사진·파일 {stats.media:,}건")
    if stats.emoticon:
        extras.append(f"이모티콘 {stats.emoticon:,}건")
    if stats.deleted:
        extras.append(f"삭제된 메시지 {stats.deleted:,}건")
    if stats.system:
        extras.append(f"입·퇴장 알림 {stats.system:,}건")
    if extras:
        lines.append("그 밖에: " + ", ".join(extras))
    busiest = stats.busiest_day
    if busiest:
        lines.append(f"가장 활발했던 날: {busiest[0]:%Y-%m-%d} ({busiest[1]:,}건)")
    peak = stats.peak_hour
    if peak:
        lines.append(f"주로 대화한 시간대: {peak[0]}시 ({peak[1]:,}건)")
    counts = {key: len(summary.hits.get(key) or []) for key in CATEGORY_ORDER}
    found = [f"{CATEGORY_LABELS[k]} {v}건" for k, v in counts.items() if v]
    if found:
        lines.append("찾아낸 항목: " + ", ".join(found))
    return lines


def _hour_chart(summary: Summary) -> list[str]:
    per_hour = summary.stats.per_hour
    if not per_hour:
        return []
    top = max(per_hour.values())
    rows = []
    for hour in range(24):
        count = per_hour.get(hour, 0)
        if count == 0 and not rows:
            continue
        rows.append((hour, count))
    while rows and rows[-1][1] == 0:
        rows.pop()
    return [f"{hour:02d}시 {_bar(count, top):<20} {count:,}" for hour, count in rows]
