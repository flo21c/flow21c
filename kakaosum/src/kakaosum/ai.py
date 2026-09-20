"""Claude 를 써서 자연어 요약을 덧붙이는 선택 기능.

기본 요약(규칙 기반)은 이 모듈 없이도 동작한다. ``--ai`` 를 줬을 때만 쓰이며,
이때 대화 내용이 Anthropic API 로 전송된다는 점을 CLI 가 미리 알린다.

    pip install "kakaosum[ai]"
    export ANTHROPIC_API_KEY=sk-ant-...
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyze import redact as redact_text
from .models import KIND_SYSTEM, ChatLog

DEFAULT_MODEL = "claude-opus-5"

#: 한 번에 보낼 대화 분량(글자 수). 넘으면 나눠 요약한 뒤 합친다.
DEFAULT_CHUNK_CHARS = 120_000

SYSTEM_PROMPT = """\
당신은 카카오톡 대화 기록을 정리해 주는 한국어 요약 도우미입니다.
주어진 대화만 근거로 삼고, 추측하거나 없는 내용을 지어내지 마세요.
확실하지 않은 부분은 '불분명'이라고 적습니다.

다음 형식의 마크다운으로 답하세요. 해당하는 내용이 없는 항목은 통째로 생략합니다.

**핵심 요약**
- 대화 전체를 3~5줄로. 무엇을 이야기했고 어디까지 진행됐는지.

**주제별 정리**
- 주제 이름: 오간 이야기와 결론을 2~3줄로. 주제는 3~6개.

**결정된 것**
- 결정 내용 (누가, 언제 정했는지 알 수 있으면 함께)

**할 일**
- 담당자 — 할 일 (기한이 있으면 기한)

**일정**
- 날짜/시간 — 무엇

**확인이 필요한 것**
- 질문만 오가고 답이 없었거나, 결론이 나지 않은 사안

이름은 대화에 나온 그대로 쓰고, 개인정보(전화번호·주소·계좌)는 요약에 옮기지 마세요.\
"""

CHUNK_PROMPT = """\
아래는 긴 대화의 일부({index}/{total})입니다. 이 부분에서 나온 내용만 정리하세요.
뒤에서 전체를 합칠 것이므로, 결정·할 일·일정·미해결 사안을 빠짐없이 적되 간결하게 쓰세요.

{transcript}\
"""

SINGLE_PROMPT = """\
아래 카카오톡 대화를 정리해 주세요.

{transcript}\
"""

MERGE_PROMPT = """\
아래는 같은 대화를 시간 순서대로 나눠 정리한 부분 요약들입니다.
중복을 합치고 시간 순서를 살려서, 하나의 요약으로 다시 정리해 주세요.

{parts}\
"""


class AIError(RuntimeError):
    """AI 요약을 만들지 못했을 때."""


@dataclass
class AIResult:
    text: str
    model: str
    chunks: int


def build_transcript(log: ChatLog, *, include_system: bool = False, redact: bool = False) -> str:
    """모델에 보낼 대화 원문을 한 줄씩 정리한다."""
    lines: list[str] = []
    last_day = None
    for m in log.messages:
        if m.kind == KIND_SYSTEM and not include_system:
            continue
        if m.dt and m.dt.date() != last_day:
            last_day = m.dt.date()
            lines.append(f"\n[{last_day:%Y-%m-%d}]")
        stamp = f"{m.dt:%H:%M}" if m.dt else "--:--"
        text = " ".join(m.text.split())
        if redact:
            text = redact_text(text)
        who = m.sender or "시스템"
        lines.append(f"{stamp} {who}: {text}")
    return "\n".join(lines).strip()


def split_transcript(transcript: str, chunk_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    """너무 길면 줄 단위로 나눈다."""
    if len(transcript) <= chunk_chars:
        return [transcript]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in transcript.splitlines():
        if size + len(line) + 1 > chunk_chars and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _client(api_key: str | None):
    try:
        import anthropic  # noqa: PLC0415 - 선택 의존성이라 늦게 불러온다
    except ImportError as exc:  # pragma: no cover - 설치 여부에 따른 분기
        raise AIError(
            "AI 요약에는 anthropic 패키지가 필요합니다.\n"
            '  pip install "kakaosum[ai]"\n'
            "  (실행파일에는 들어 있지 않습니다. 파이썬으로 설치해 주세요.)"
        ) from exc
    try:
        return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    except Exception as exc:  # pragma: no cover - 자격 증명 문제
        raise AIError(
            "Anthropic 클라이언트를 만들지 못했습니다. ANTHROPIC_API_KEY 를 확인해 주세요.\n"
            f"  원인: {exc}"
        ) from exc


def _ask(client, model: str, prompt: str, *, max_tokens: int = 8000) -> str:
    """메시지 한 번 주고받기. 정책상 거절되면 서버 쪽 대체 모델로 이어 간다."""
    import anthropic  # noqa: PLC0415

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        with client.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
        ) as stream:
            message = stream.get_final_message()
    except (anthropic.BadRequestError, TypeError):
        # 대체 모델 기능을 쓸 수 없는 환경이면 그냥 보낸다
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
    except anthropic.APIError as exc:
        raise AIError(f"Anthropic API 호출에 실패했습니다: {exc}") from exc

    if getattr(message, "stop_reason", None) == "refusal":
        raise AIError("모델이 이 대화의 요약을 거절했습니다.")
    text = "\n".join(b.text for b in message.content if b.type == "text").strip()
    if not text:
        raise AIError("모델이 빈 응답을 돌려줬습니다.")
    return text


def summarize_with_claude(
    log: ChatLog,
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    redact: bool = False,
) -> AIResult:
    """대화를 Claude 에 보내 자연어 요약을 받는다."""
    transcript = build_transcript(log, redact=redact)
    if not transcript:
        raise AIError("요약할 대화 내용이 없습니다.")

    client = _client(api_key)
    chunks = split_transcript(transcript, chunk_chars)

    if len(chunks) == 1:
        return AIResult(_ask(client, model, SINGLE_PROMPT.format(transcript=chunks[0])), model, 1)

    parts = [
        _ask(
            client,
            model,
            CHUNK_PROMPT.format(index=i, total=len(chunks), transcript=chunk),
            max_tokens=4000,
        )
        for i, chunk in enumerate(chunks, start=1)
    ]
    joined = "\n\n---\n\n".join(f"[부분 {i}]\n{p}" for i, p in enumerate(parts, start=1))
    merged = _ask(client, model, MERGE_PROMPT.format(parts=joined))
    return AIResult(merged, model, len(chunks))
