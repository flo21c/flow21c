# FlowMind 앱 소스

윈도우용 마인드맵 노트 앱 FlowMind (Electron 33.4.11) 의 소스입니다.

> 이 소스는 PC 포맷으로 원본이 사라진 뒤, 배포된 v1.0.0 설치 파일(`FlowMind-Setup-1.0.0.exe`)
> 안의 `resources/app.asar` 에서 되살린 것입니다. 앱 코드(주석 포함)는 원본 그대로이며,
> `package.json` 의 빌드 설정과 `tools/keygen.js` 는 새로 작성했습니다.

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `main.js` | 메인 프로세스 (창, 파일 저장/열기, 기기 코드, 인증 검사) |
| `preload.js` | 렌더러에 열어 주는 API (`window.flowmind`) |
| `license-core.js` | 인증키 생성 규칙 (앱과 발급 도구가 함께 씀) |
| `license-secret.js` | **인증키 비밀값 — 저장소에 없음, 직접 만들어야 함** |
| `renderer/` | 화면 (index.html, app.js, license.js, style.css) |
| `build/icon.ico` | 앱 아이콘 |
| `tools/keygen.js` | 판매자용 인증키 발급 도구 |

## 처음 준비 (Windows)

1. [Node.js](https://nodejs.org) LTS 설치
2. 이 폴더에 `license-secret.js` 를 만들고 아래 한 줄을 넣습니다 (값은 따로 보관한 비밀값):

   ```js
   module.exports = '64자리 16진수 비밀값';
   ```

   이 파일은 `.gitignore` 에 들어 있어 커밋되지 않습니다. 값이 바뀌면 이미 발급한 인증키가 모두 무효가 되니
   반드시 기존 값을 그대로 쓰세요.
3. `npm install`

## 명령

```bat
npm start                       :: 앱 실행 (개발용)
npm run dist                    :: dist\ 에 FlowMind-Setup-x.y.z.exe, FlowMind-x.y.z-portable.exe 생성
npm run keygen -- ABCD-1234-EF56-7890   :: 고객 기기 코드로 인증키 발급
```

새 버전을 낼 때는 `package.json` 의 `version` 을 올린 뒤 `npm run dist` 하고,
만든 exe 를 GitHub 릴리스에 올린 다음 저장소 루트 `index.html` 의 주소·SHA256 값을 바꿉니다
(`certutil -hashfile 파일이름 SHA256`).
