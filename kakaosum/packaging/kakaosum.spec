# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 설정.

    pyinstaller --noconfirm --clean packaging/kakaosum.spec

dist/ 아래에 두 개가 만들어진다.
  kakaosum      : 명령줄용 (콘솔 창). 파일을 끌어다 놓으면 바로 요약한다.
  kakaosum-gui  : 창으로 쓰는 버전.
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent          # noqa: F821 - SPECPATH 는 PyInstaller 가 넣어 준다
SRC = str(ROOT / "src")
PACKAGING = ROOT / "packaging"

# 쓰지 않는 무거운 라이브러리는 빼서 파일 크기를 줄인다
COMMON_EXCLUDES = ["numpy", "pandas", "matplotlib", "PIL", "pytest", "setuptools", "pip"]

cli_analysis = Analysis(  # noqa: F821
    [str(PACKAGING / "entry_cli.py")],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[*COMMON_EXCLUDES, "tkinter"],
    noarchive=False,
)
cli_pyz = PYZ(cli_analysis.pure)  # noqa: F821
cli_exe = EXE(  # noqa: F821
    cli_pyz,
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.datas,
    [],
    name="kakaosum",
    console=True,
    debug=False,
    strip=False,
    upx=False,
    bootloader_ignore_signals=False,
    disable_windowed_traceback=False,
)

gui_analysis = Analysis(  # noqa: F821
    [str(PACKAGING / "entry_gui.py")],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
    hookspath=[],
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
)
gui_pyz = PYZ(gui_analysis.pure)  # noqa: F821
gui_exe = EXE(  # noqa: F821
    gui_pyz,
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.datas,
    [],
    name="kakaosum-gui",
    console=False,          # 창 모드: 검은 콘솔이 같이 뜨지 않는다
    debug=False,
    strip=False,
    upx=False,
    bootloader_ignore_signals=False,
    disable_windowed_traceback=False,
)
