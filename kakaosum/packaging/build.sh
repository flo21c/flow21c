#!/usr/bin/env bash
# 리눅스 / macOS 에서 실행파일 만들기
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip pyinstaller
python3 -m pip install .
python3 -m PyInstaller --noconfirm --clean packaging/kakaosum.spec

echo
echo "완성됐습니다:"
ls -lh dist/ | tail -n +2
