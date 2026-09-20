"""PyInstaller 로 만들 창(GUI) 실행파일의 시작점."""

import sys

from kakaosum.gui import main

if __name__ == "__main__":
    sys.exit(main())
