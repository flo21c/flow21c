"""대화 내용을 통계 · 키워드 · 항목별로 뽑아내는 분석기.

형태소 분석기 같은 외부 라이브러리 없이, 한국어 채팅에서 자주 쓰이는
조사 · 어미 패턴만 걷어내는 가벼운 방식으로 동작한다. 설치가 간단한 대신
완벽한 형태소 분석은 아니며, 요약의 '단서'를 찾는 용도로 충분하도록 맞췄다.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .models import KIND_DELETED, KIND_EMOTICON, KIND_MEDIA, KIND_SYSTEM, ChatLog, Message

WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")

# 키워드에서 빼는 채팅 군더더기
STOPWORDS = frozenset("""
그래 그건 그거 그럼 그리고 그래서 그러면 그런데 근데 하지만 그냥 진짜 정말 완전 제일 많이 조금
지금 이제 아직 벌써 다시 혹시 아마 역시 그때 여기 저기 거기 이거 저거 요거 무슨 어떤 어디 언제
감사 감사합니다 고맙습니다 죄송 죄송합니다 안녕하세요 안녕히 수고 수고하셨습니다 넵넵 알겠습니다
생각 얘기 이야기 말씀 부분 경우 정도 문제 내용 사람 사진 동영상 이모티콘 카톡 카카오톡 메시지
오늘 내일 모레 어제 오전 오후 시간 우리 저희 자기 당신 여러분 하나 가지 이번 다음 지난 매우
같이 함께 먼저 나중 이상 이하 관련 확인 가능 필요 그전 오래 대해 대한 위해 통해 보니 보면
저는 제가 저희 우리 그건 그게 이게 저게 전에 후에 그런 이런 저런 그램 뭔가 뭐가 일단 다들
좋은 좋을 좋다 괜찮 부분들 이건 저건 그거야 어제는 오늘은 내일은 이거는 그러면
""".split())

# 명사 뒤에 자주 붙는 조사 (긴 것부터)
JOSA = (
    "에서는", "에게서", "한테서", "으로는", "이라고", "라고는", "에서도", "에게는", "이라는",
    "으로써", "으로서", "이라도", "까지는", "부터는", "만큼은", "처럼은",
    "에서", "에게", "한테", "께서", "까지", "부터", "보다", "처럼", "만큼", "으로", "라고",
    "이나", "이랑", "이며", "이다", "이고", "이라", "에는", "에도", "에요", "예요",
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "만", "로", "님",
)
# 동사·형용사 활용형으로 보이는 꼬리
VERB_TAIL_RE = re.compile(
    r"(니다|하세요|해주세요|주세요|드립니다|드려요|같아요|같습니다"
    r"|하는|했던|해서|하고|해요|했어|했죠|하죠|네요|어요|아요|군요|거든요|더라고요|되나요|인가요"
    r"|합시다|갑시다|봅시다|하시죠|보시죠|할까요|일까요|겠네요|되네요|해야|하면|되면"
    r"|게요|겠어요|더라고|했고|됐고|하네|하죠|이죠|예요|네요|까요|나요|가요)$"
)
# 숫자에 붙은 단위 (3시, 20일, 5명 …) - 키워드로는 쓸모가 없어 통째로 걷어낸다
NUM_UNIT_RE = re.compile(
    r"\d+\s*만?\s*(?:시간|분간|개월|시|분|초|일|월|년|개|명|장|번|차|원|층|주|%|퍼센트|kg|km|cm|mm)"
)
# '확정해야', '출시하는' 처럼 '-하다/-되다' 가 붙은 말에서 앞의 명사만 남긴다
HADA_STEM_RE = re.compile(
    r"^(?P<stem>[가-힣]{2,})"
    r"(?:하는|하고|하기|하면|하며|하러|하죠|하자|하네|한다|했다|했고|했던|했는데|하는데"
    r"|해야|해서|해요|해줘|해주세요|해주시면|해주실|했어요|했습니다|합니다|할게요|할까요"
    r"|하겠습니다|하겠어요|되는|되고|된다|됩니다|됐어요|됐고|되어|돼서|되면|됐습니다)$"
)
HANGUL_WORD_RE = re.compile(r"[가-힣]{2,}")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._-]{1,}")

URL_RE = re.compile(r"https?://[^\s<>()\[\]]+|www\.[^\s<>()\[\]]+")
MONEY_RE = re.compile(r"\d[\d,]*\s*(?:원|만원|천원|억원|억|달러|USD|불)")
PHONE_RE = re.compile(r"01[016-9][-. ]?\d{3,4}[-. ]?\d{4}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

DATE_MENTION_RE = re.compile(
    r"(?:\d{1,2}\s*월\s*\d{1,2}\s*일"
    r"|\d{1,2}/\d{1,2}(?!\d)"
    r"|(?:이번|다음|담|저번|지난)\s*주(?:\s*[월화수목금토일]요일)?"
    r"|[월화수목금토일]요일"
    r"|오늘|내일|모레|글피|주말|평일|월말|월초|연휴"
    r"|(?:오전|오후|아침|점심|저녁|밤)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?"
    r"|\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?(?:\s*까지|\s*에|\s*부터)?)"
)

DECISION_RE = re.compile(
    r"(하기로\s*(?:했|하|합|해)|가기로|정하기로|쓰기로|보기로"
    r"|결정(?:했|됐|되었|하|입니다|됨)|확정(?:했|됐|되었|입니다|임|됨)"
    r"|(?:하|가|쓰|보)는\s*걸로|하는걸로|그렇게\s*(?:하|가)"
    r"|합시다|하시죠|하죠|갑시다|진행(?:하기로|합니다|할게|하겠)"
    r"|최종|결론|확정안|승인(?:했|됐|되었|합니다))"
)
TODO_RE = re.compile(
    r"(해\s*주세요|해주세요|해줘|해줄래|부탁(?:드립니다|드려요|합니다|해요|해|드릴게)"
    r"|준비(?:해|하고|할게|해주|부탁|가 필요)|정리(?:해|해서|할게|부탁)"
    r"|확인(?:해|부탁|좀|바랍|하겠|할게)|보내(?:주세요|드릴게|줘|겠습니다|드리겠)"
    r"|올려(?:주세요|줘|드릴게)|공유(?:해|부탁|드릴게|하겠)"
    r"|담당|맡아|맡을|처리(?:해|부탁|하겠|할게)|작성(?:해|부탁|하겠|할게)"
    r"|까지\s*(?:해|완료|제출|보내|끝|마무리)|하겠습니다|할게요|할게|드릴게요)"
)
QUESTION_RE = re.compile(
    r"(\?|까요|나요|인가요|가요\s*$|어때|언제|어디|누가|누구|얼마|몇\s*(?:시|명|개|일)"
    r"|될까|되나|맞나|맞아|가능(?:한가|할까|해))"
)

CATEGORY_LABELS = {
    "decision": "결정된 것",
    "todo": "할 일",
    "schedule": "일정 · 날짜",
    "question": "답 없는 질문",
    "link": "공유된 링크",
    "money": "금액 언급",
}


def normalize_token(token: str) -> str | None:
    """조사 · 어미를 털어낸 키워드 후보. 버릴 토큰이면 None."""
    word = token.strip()
    if not word:
        return None
    if LATIN_WORD_RE.fullmatch(word):
        return word.lower() if len(word) >= 2 else None
    if not HANGUL_WORD_RE.fullmatch(word):
        return None
    stem = HADA_STEM_RE.match(word)
    if stem:
        candidate = stem.group("stem")
        return candidate if candidate not in STOPWORDS else None
    if VERB_TAIL_RE.search(word):
        return None
    for josa in JOSA:
        if word.endswith(josa) and len(word) - len(josa) >= 2:
            word = word[: -len(josa)]
            break
    if len(word) < 2 or word in STOPWORDS:
        return None
    return word


def tokenize(text: str) -> list[str]:
    """메시지 한 건에서 키워드 후보를 뽑는다."""
    cleaned = NUM_UNIT_RE.sub(" ", URL_RE.sub(" ", text))
    raw = HANGUL_WORD_RE.findall(cleaned) + LATIN_WORD_RE.findall(cleaned)
    out = []
    for token in raw:
        norm = normalize_token(token)
        if norm:
            out.append(norm)
    return out


@dataclass
class Keyword:
    word: str
    count: int
    speakers: int

    def to_dict(self) -> dict:
        return {"word": self.word, "count": self.count, "speakers": self.speakers}


def keywords(messages: list[Message], top_n: int = 15, min_count: int = 2) -> list[Keyword]:
    """많이 쓰인 낱말을 뽑는다. 여러 사람이 쓴 낱말을 우선한다."""
    counts: Counter[str] = Counter()
    speakers: defaultdict[str, set[str]] = defaultdict(set)
    for m in messages:
        if m.kind == KIND_SYSTEM:
            continue
        for token in set(tokenize(m.text)):  # 한 메시지에서 같은 낱말은 한 번만
            counts[token] += 1
            speakers[token].add(m.sender)
    ranked = sorted(
        (Keyword(w, c, len(speakers[w])) for w, c in counts.items() if c >= min_count),
        key=lambda k: (-k.count, -k.speakers, k.word),
    )
    if not ranked:  # 짧은 대화에서는 1회 등장도 보여 준다
        ranked = sorted(
            (Keyword(w, c, len(speakers[w])) for w, c in counts.items()),
            key=lambda k: (-k.count, -k.speakers, k.word),
        )
    return ranked[:top_n]


@dataclass
class ParticipantStat:
    name: str
    messages: int = 0
    chars: int = 0
    media: int = 0
    questions: int = 0
    first: datetime | None = None
    last: datetime | None = None
    share: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "messages": self.messages,
            "chars": self.chars,
            "media": self.media,
            "questions": self.questions,
            "share": round(self.share, 3),
            "first": self.first.isoformat() if self.first else None,
            "last": self.last.isoformat() if self.last else None,
        }


@dataclass
class Stats:
    total: int = 0
    speech: int = 0
    system: int = 0
    media: int = 0
    emoticon: int = 0
    deleted: int = 0
    chars: int = 0
    start: datetime | None = None
    end: datetime | None = None
    active_days: int = 0
    span_days: int = 0
    participants: list[ParticipantStat] = field(default_factory=list)
    per_day: dict[date, int] = field(default_factory=dict)
    per_hour: dict[int, int] = field(default_factory=dict)
    per_weekday: dict[int, int] = field(default_factory=dict)

    @property
    def busiest_day(self) -> tuple[date, int] | None:
        return max(self.per_day.items(), key=lambda kv: (kv[1], kv[0])) if self.per_day else None

    @property
    def peak_hour(self) -> tuple[int, int] | None:
        return max(self.per_hour.items(), key=lambda kv: (kv[1], -kv[0])) if self.per_hour else None

    @property
    def messages_per_active_day(self) -> float:
        return self.speech / self.active_days if self.active_days else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "speech": self.speech,
            "system": self.system,
            "media": self.media,
            "emoticon": self.emoticon,
            "deleted": self.deleted,
            "chars": self.chars,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "active_days": self.active_days,
            "span_days": self.span_days,
            "messages_per_active_day": round(self.messages_per_active_day, 1),
            "busiest_day": (
                {"date": self.busiest_day[0].isoformat(), "messages": self.busiest_day[1]}
                if self.busiest_day
                else None
            ),
            "peak_hour": (
                {"hour": self.peak_hour[0], "messages": self.peak_hour[1]} if self.peak_hour else None
            ),
            "participants": [p.to_dict() for p in self.participants],
            "per_day": {d.isoformat(): n for d, n in sorted(self.per_day.items())},
            "per_hour": {str(h): self.per_hour.get(h, 0) for h in range(24)},
            "per_weekday": {WEEKDAYS[i]: self.per_weekday.get(i, 0) for i in range(7)},
        }


def compute_stats(log: ChatLog) -> Stats:
    """참여자별 · 시간대별 기본 통계."""
    stats = Stats(total=len(log.messages), start=log.start, end=log.end)
    people: dict[str, ParticipantStat] = {}

    for m in log.messages:
        if m.kind == KIND_SYSTEM:
            stats.system += 1
            continue
        stats.speech += 1
        stats.chars += len(m.text)
        if m.kind == KIND_MEDIA:
            stats.media += 1
        elif m.kind == KIND_EMOTICON:
            stats.emoticon += 1
        elif m.kind == KIND_DELETED:
            stats.deleted += 1

        person = people.setdefault(m.sender, ParticipantStat(m.sender))
        person.messages += 1
        person.chars += len(m.text)
        if m.kind == KIND_MEDIA:
            person.media += 1
        if QUESTION_RE.search(m.text):
            person.questions += 1
        if m.dt:
            person.first = min(person.first or m.dt, m.dt)
            person.last = max(person.last or m.dt, m.dt)
            day = m.dt.date()
            stats.per_day[day] = stats.per_day.get(day, 0) + 1
            stats.per_hour[m.dt.hour] = stats.per_hour.get(m.dt.hour, 0) + 1
            stats.per_weekday[day.weekday()] = stats.per_weekday.get(day.weekday(), 0) + 1

    for person in people.values():
        person.share = person.messages / stats.speech if stats.speech else 0.0
    stats.participants = sorted(people.values(), key=lambda p: (-p.messages, p.name))
    stats.active_days = len(stats.per_day)
    if stats.start and stats.end:
        stats.span_days = (stats.end.date() - stats.start.date()).days + 1
    return stats


@dataclass
class Hit:
    """요약에 쓸 만한 한 줄."""

    category: str
    message: Message
    snippet: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "datetime": self.message.dt.isoformat() if self.message.dt else None,
            "sender": self.message.sender,
            "text": self.message.text,
            "snippet": self.snippet,
        }


def _one_line(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def find_hits(log: ChatLog, *, answer_window_minutes: int = 120) -> list[Hit]:
    """결정 · 할 일 · 일정 · 링크 · 금액 · 답 없는 질문을 찾아낸다."""
    hits: list[Hit] = []
    speech = [m for m in log.messages if m.kind != KIND_SYSTEM]
    window = timedelta(minutes=answer_window_minutes)

    for i, m in enumerate(speech):
        text = m.text
        if not text.strip():
            continue
        line = _one_line(text)
        if DECISION_RE.search(text):
            hits.append(Hit("decision", m, line))
        if TODO_RE.search(text):
            hits.append(Hit("todo", m, line))
        if DATE_MENTION_RE.search(text) and len(text) > 4:
            hits.append(Hit("schedule", m, line))
        for url in URL_RE.findall(text):
            hits.append(Hit("link", m, url))
        for money in MONEY_RE.findall(text):
            hits.append(Hit("money", m, line))
        if QUESTION_RE.search(text) and not _answered(speech, i, window):
            hits.append(Hit("question", m, line))
    return hits


def _answered(speech: list[Message], index: int, window: timedelta) -> bool:
    """질문 뒤 일정 시간 안에 다른 사람이 답했는지."""
    asker = speech[index].sender
    asked_at = speech[index].dt
    for later in speech[index + 1 : index + 40]:
        if later.sender == asker:
            continue
        if asked_at and later.dt and later.dt - asked_at > window:
            return False
        return True
    return False


def group_hits(hits: list[Hit]) -> dict[str, list[Hit]]:
    """카테고리별로 묶되 같은 메시지가 중복되지 않게 한다."""
    grouped: dict[str, list[Hit]] = {key: [] for key in CATEGORY_LABELS}
    seen: dict[str, set[tuple]] = {key: set() for key in CATEGORY_LABELS}
    for hit in hits:
        key = (hit.message.line_no, hit.snippet)
        if key in seen[hit.category]:
            continue
        seen[hit.category].add(key)
        grouped[hit.category].append(hit)
    return grouped


def has_contact_info(log: ChatLog) -> bool:
    """전화번호 · 이메일이 들어 있는지 (개인정보 주의 안내용)."""
    return any(PHONE_RE.search(m.text) or EMAIL_RE.search(m.text) for m in log.messages)


def redact(text: str) -> str:
    """전화번호 · 이메일을 가린다."""
    text = PHONE_RE.sub("010-****-****", text)
    return EMAIL_RE.sub("***@***", text)
