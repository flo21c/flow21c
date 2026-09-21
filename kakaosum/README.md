# kakaosum — 카카오톡 대화 요약기

카카오톡에서 내보낸 대화 `.txt` 파일을 읽어 **누가 · 언제 · 무엇을 이야기했는지**
정리해 주는 명령줄 도구이자 파이썬 라이브러리입니다.

* 기본 요약은 **인터넷 없이** 동작합니다. 대화 내용이 밖으로 나가지 않습니다.
* 안드로이드 · 아이폰 · PC(윈도우) 내보내기 형식을 모두 읽습니다.
* 결정된 것, 할 일, 일정, 답이 없는 질문, 공유된 링크, 금액 언급을 자동으로 뽑아냅니다.
* `--ai` 를 붙이면 Claude 가 쓴 자연어 요약을 덧붙일 수 있습니다. (선택)

## 웹페이지로 쓰기 (설치 없이)

`web/index.html` 파일 한 장이면 됩니다. **더블클릭해서 브라우저로 열고**, 대화 `.txt` 를
끌어다 놓으면 바로 요약이 나옵니다. 붙여넣기도 됩니다.

* 파싱 · 분석 · 요약이 **전부 브라우저 안에서** 돌아갑니다. 서버로 아무것도 보내지 않으며,
  인터넷이 끊겨 있어도 동작합니다. (글꼴만 인터넷에서 받아 오고, 없으면 시스템 글꼴로 나옵니다)
* PC 내보내기의 `cp949` 파일도 알아서 읽습니다.
* 결과는 **마크다운 복사** 또는 **.md 저장** 으로 가져갈 수 있습니다.
* 명령줄 버전과 같은 규칙으로 계산합니다. 같은 파일을 넣으면 같은 숫자가 나옵니다.

GitHub Pages 를 쓴다면 이 파일을 그대로 올려도 됩니다. 따로 빌드할 것이 없습니다.

## 실행파일로 쓰기 (파이썬 설치 없이)

실행파일은 두 가지가 만들어집니다.

| 파일 | 쓰는 법 |
|---|---|
| `kakaosum.exe` | 대화 `.txt` 를 **이 파일 위로 끌어다 놓으면** 바로 요약이 화면에 나옵니다. 그냥 더블클릭하면 파일 경로를 물어보고, 원본 옆에 `대화_요약.md` 로 저장합니다. 명령줄 옵션도 그대로 씁니다. |
| `kakaosum-gui.exe` | 창이 열립니다. 파일 고르기 → 옵션 선택 → **요약 만들기** → 저장/복사. |

### 받기

1. 저장소의 **Releases** 에 올라온 파일을 내려받거나,
2. **Actions → kakaosum 실행파일 빌드 → Run workflow** 를 돌린 뒤 결과(Artifacts)를 내려받습니다.
   `kakaosum-v0.1.0` 같은 태그를 밀면 빌드 후 릴리스에 자동으로 붙습니다.

```bash
git tag kakaosum-v0.1.0 && git push origin kakaosum-v0.1.0
```

### 직접 만들기 (윈도우)

1. [python.org](https://www.python.org/downloads/) 에서 파이썬을 설치합니다.
   설치 화면의 **"Add python.exe to PATH"** 를 꼭 체크하세요. (이미 있으면 넘어갑니다)
2. 이 폴더의 `packaging\build.bat` 을 **더블클릭**합니다.
3. 2~3분 뒤 `dist\` 폴더가 열리고, 안에 실행파일 두 개가 있습니다.

```bat
packaging\build.bat
```

빌드에 필요한 것들은 `.build-venv` 폴더(가상환경) 안에만 설치되므로
**시스템 파이썬은 건드리지 않습니다.** 실패하면 `build-log.txt` 에 원인이 남습니다.
리눅스·macOS 는 `packaging/build.sh` 로 같은 일을 합니다.

만들어진 실행파일은 그 폴더만 있으면 어디서든 돌아갑니다. 파이썬이 없는
다른 컴퓨터로 `kakaosum.exe` 하나만 복사해 가도 동작합니다.

> 서명하지 않은 실행파일이라 윈도우에서 "PC 보호" 경고가 뜰 수 있습니다.
> *추가 정보 → 실행* 으로 넘어가거나, FlowMind 설치 파일처럼 코드 서명을 붙이면 됩니다.

## 설치 (파이썬으로 쓰기)

```bash
cd kakaosum
pip install -e .            # 기본 (의존성 없음, 파이썬 3.10+)
pip install -e ".[ai]"      # AI 요약까지 쓰려면
```

## 대화 내보내기

| 기기 | 방법 |
|---|---|
| 안드로이드 | 채팅방 → 메뉴(≡) → 설정(⚙) → **대화 내용 내보내기** → *텍스트만 보내기* |
| 아이폰 | 채팅방 → 메뉴(≡) → 설정(⚙) → **대화 내용 내보내기** → *텍스트 파일로 내보내기* |
| PC | 채팅방 우클릭 또는 창 상단 메뉴 → **대화 내용 저장** |

저장된 `.txt` 파일을 그대로 넣으면 됩니다. (PC 에서 저장한 `cp949` 파일도 읽습니다.)

## 사용법

```bash
kakaosum summarize 대화.txt                    # 화면에 요약 출력 (마크다운)
kakaosum summarize 대화.txt -o 요약.md         # 파일로 저장
kakaosum summarize 대화.txt --last-days 7      # 최근 7일만
kakaosum summarize 대화.txt --group session    # 날짜 대신 '대화 덩어리' 단위로
kakaosum summarize 대화.txt -f text            # 꾸밈 없는 텍스트
kakaosum summarize 대화.txt -f json            # 프로그램에서 쓰기 좋은 JSON
kakaosum summarize 대화.txt --mask --redact    # 이름·연락처 가리기
kakaosum stats 대화.txt                        # 통계만
kakaosum export 대화.txt -f csv -o 대화.csv    # 파싱 결과를 표로 내보내기
cat 대화.txt | kakaosum summarize -            # 표준 입력도 가능
```

### 자주 쓰는 옵션

| 옵션 | 설명 |
|---|---|
| `--since / --until YYYY-MM-DD` | 기간 지정 |
| `--last-days N` | 마지막 대화일 기준 최근 N일 |
| `--sender 이름` | 특정 사람 메시지만 (여러 번 지정 가능) |
| `--group day\|session\|none` | 날짜별 / 대화 덩어리별 / 구간 나누지 않음 |
| `--top-keywords N`, `--max-items N` | 키워드 수, 항목별 줄 수 |
| `--answer-window 분` | 이 시간 안에 답이 없으면 '답 없는 질문'으로 봄 (기본 120분) |
| `--mask` | 참여자 이름을 `참여자 A` 로 익명화 |
| `--redact` | 전화번호 · 이메일 가리기 |
| `--no-system` | 입·퇴장 알림 제외 |
| `--ai`, `--ai-model` | Claude 자연어 요약 (기본 모델 `claude-opus-5`) |

## 결과 예시

`samples/sample_android.txt` 를 요약하면 이렇게 나옵니다. (일부)

```markdown
# 카카오톡 대화 요약 — 플로우마인드 개발팀

> 2026-09-01 ~ 2026-09-04 사이 3명이 나눈 대화 33건 (대화가 오간 날 3일)

## 한눈에 보기

- 기간: 2026-09-01 09:12 ~ 2026-09-04 15:12 (4일 중 3일 대화)
- 메시지: 33건 · 하루 평균 11.0건 · 글자 수 780자
- 가장 활발했던 날: 2026-09-01 (14건)
- 찾아낸 항목: 결정된 것 3건, 할 일 7건, 일정 · 날짜 9건, 공유된 링크 1건

## 결정된 것

- [09-01 09:25] 박지훈: 그럼 오후 3시에 하기로 하죠
- [09-02 18:20] 김서연: 체험 기간 문구는 "설치하면 24시간 무료로 써보실 수 있습니다" 로 확정했습니다
- [09-04 15:00] 박지훈: 두 개 다 잘 되네요. 다음 주 월요일에 1.1 배포하기로 합시다

## 할 일

- [09-01 09:26] 김서연: 회의 전에 지난 버전 피드백 정리해서 공유드릴게요
- [09-04 15:05] 이민호: 배포 전에 설치 파일 서명도 확인해야 합니다
```

## AI 요약 (선택)

규칙 기반 요약은 "대화에서 이런 줄들이 중요해 보인다"까지만 해 줍니다.
문장으로 된 요약이 필요하면 `--ai` 를 쓰세요.

```bash
pip install -e ".[ai]"
export ANTHROPIC_API_KEY=sk-ant-...      # 윈도우: set ANTHROPIC_API_KEY=...
kakaosum summarize 대화.txt --ai -o 요약.md
```

* **대화 내용이 Anthropic API 로 전송됩니다.** 실행 전에 한 번 물어보며, `--yes` 로 생략할 수 있습니다.
* `--redact` 와 `--mask` 를 함께 쓰면 연락처와 이름을 가린 상태로 보냅니다.
* 대화가 길면 여러 조각으로 나눠 요약한 뒤 하나로 합칩니다.
* 기본 모델은 `claude-opus-5` 이고, `--ai-model` 로 바꿀 수 있습니다.

## 개인정보

* 기본 동작은 전부 내 컴퓨터 안에서 끝납니다. 어떤 서버에도 접속하지 않습니다.
* 대화에 전화번호나 이메일이 있으면 요약 아래 '참고'에 알려 줍니다.
* 남에게 보낼 요약이라면 `--mask --redact` 를 권합니다.
* 대화 당사자가 아닌 사람의 대화를 동의 없이 정리·공유하는 일은 피해 주세요.

## 파이썬에서 쓰기

```python
from kakaosum import parse_file, summarize, render

log = parse_file("대화.txt")
recent = log.last_days(30)

summary = summarize(recent, group="day", top_keywords=20)
print(summary.headline)
print(render(summary, "markdown"))

# 원하는 부분만 직접 꺼내 쓰기
for hit in summary.hits["todo"]:
    print(hit.message.dt, hit.message.sender, hit.snippet)
```

주요 객체는 `ChatLog`(대화 전체) · `Message`(한 줄) · `Summary`(요약 결과)이며,
`summary.to_dict()` 로 JSON 으로 만들 수 있습니다.

## 읽을 수 있는 형식

```
[홍길동] [오후 1:23] 메시지                       안드로이드 · PC 최신
2026년 9월 1일 오후 1:23, 홍길동 : 메시지         아이폰 · PC 구버전
2026. 9. 1. 오후 1:23, 홍길동 : 메시지            아이폰 변형
[홍길동] [13:23] / [1:23 PM] 메시지               24시간 · 영문 표기
```

여러 줄 메시지, 날짜 구분선, 입·퇴장 알림, 사진 / 이모티콘 / 삭제된 메시지도 구분합니다.

## 한계

* 형태소 분석기를 쓰지 않고 조사 · 어미 패턴만 걷어내므로, 키워드에 가끔 어색한 말이 섞입니다.
* '결정 · 할 일' 은 말투(`~하기로 하죠`, `~해주세요` 등)로 찾아내는 방식이라 놓치거나 더 잡을 수 있습니다.
  정확한 문장 요약이 필요하면 `--ai` 를 쓰세요.
* 카카오톡이 내보내기 형식을 바꾸면 파서 수정이 필요할 수 있습니다.

## 개발

```bash
python -m unittest discover -s tests -v      # 테스트 (의존성 없이 동작)
```

```
src/kakaosum/
  parser.py      내보내기 .txt → ChatLog
  models.py      Message / ChatLog (기간·발신자 필터, 익명화, 덩어리 나누기)
  analyze.py     통계 · 키워드 · 결정/할 일/일정 추출
  summarize.py   Summary 조립
  render.py      마크다운 · 텍스트 · JSON 출력
  ai.py          Claude 자연어 요약 (선택)
  cli.py         명령줄 인터페이스 (끌어다 놓기·대화형 모드 포함)
  gui.py         창으로 쓰는 버전 (tkinter, 표준 라이브러리)
web/
  index.html     웹페이지 버전 (파이썬 엔진을 자바스크립트로 옮긴 것, 의존성 없음)
packaging/
  kakaosum.spec  PyInstaller 빌드 설정 (콘솔용 + 창용)
  build.bat      윈도우에서 실행파일 만들기
  build.sh       리눅스·macOS 에서 실행파일 만들기
.github/workflows/
  kakaosum-test.yml   푸시할 때마다 테스트
  kakaosum-build.yml  윈도우·리눅스·macOS 실행파일 빌드 및 릴리스
```

> 참고: 실행파일에는 AI 요약용 `anthropic` 패키지가 들어 있지 않습니다.
> `--ai` 가 필요하면 파이썬으로 설치해 쓰세요.
