"""PyInstaller 로 만들 명령줄 실행파일의 시작점."""

import sys

from kakaosum.cli import main

if __name__ == "__main__":
    sys.exit(main())
