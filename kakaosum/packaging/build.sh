#!/usr/bin/env bash
# kakaosum 실행파일 만들기 (리눅스 / macOS)
# 빌드용 가상환경(.build-venv)을 따로 만들어 쓰므로 시스템 파이썬은 건드리지 않는다.
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
echo "[1/4] 파이썬 확인: $($PY -V)"

echo "[2/4] 빌드용 가상환경 준비"
[ -x ".build-venv/bin/python" ] || "$PY" -m venv .build-venv
VPY=".build-venv/bin/python"

echo "[3/4] 빌드 도구와 kakaosum 설치"
"$VPY" -m pip install --upgrade pip --quiet
"$VPY" -m pip install pyinstaller --quiet
"$VPY" -m pip install . --quiet

echo "[4/4] 실행파일 만드는 중"
"$VPY" -m PyInstaller --noconfirm --clean packaging/kakaosum.spec > build-log.txt 2>&1 || {
    echo "실행파일을 만들지 못했습니다. build-log.txt 의 마지막 20줄:"
    tail -20 build-log.txt
    exit 1
}

echo
echo "완성됐습니다:"
ls -lh dist/
echo
echo "동작 확인:"
./dist/kakaosum summarize samples/sample_android.txt -f text --group none | head -3
