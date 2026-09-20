@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title kakaosum 실행파일 만들기

rem ============================================================
rem  kakaosum 실행파일 만들기 (윈도우)
rem  이 파일을 더블클릭하면 dist 폴더에 실행파일이 만들어집니다.
rem  - 빌드용 가상환경(.build-venv)을 따로 만들어 쓰므로
rem    시스템 파이썬에는 아무것도 설치하지 않습니다.
rem ============================================================

cd /d "%~dp0.."
echo.
echo   kakaosum 실행파일을 만듭니다. 처음에는 2~3분 정도 걸립니다.
echo.

rem ---- 1) 파이썬 찾기 -----------------------------------------
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  echo   [!] 파이썬을 찾지 못했습니다.
  echo       https://www.python.org/downloads/ 에서 설치한 뒤
  echo       설치 화면의 "Add python.exe to PATH" 를 꼭 체크해 주세요.
  echo.
  pause
  exit /b 1
)
for /f "tokens=*" %%v in ('%PY% -V 2^>^&1') do echo   [1/4] 파이썬 확인: %%v

rem ---- 2) 빌드용 가상환경 -------------------------------------
echo   [2/4] 빌드용 가상환경 준비
if not exist ".build-venv\Scripts\python.exe" (
  %PY% -m venv .build-venv || goto :error
)
set "VPY=.build-venv\Scripts\python.exe"

rem ---- 3) 필요한 것 설치 --------------------------------------
echo   [3/4] 빌드 도구와 kakaosum 설치 (잠시 기다려 주세요)
"%VPY%" -m pip install --upgrade pip --quiet || goto :error
"%VPY%" -m pip install pyinstaller --quiet || goto :error
"%VPY%" -m pip install . --quiet || goto :error

rem ---- 4) 실행파일 만들기 -------------------------------------
echo   [4/4] 실행파일 만드는 중
"%VPY%" -m PyInstaller --noconfirm --clean packaging/kakaosum.spec > build-log.txt 2>&1 || goto :error_log

if not exist "dist\kakaosum.exe" goto :error_log

echo.
echo   ============================================================
echo    완성됐습니다.  dist 폴더
echo.
echo      kakaosum.exe       대화 .txt 를 이 파일 위로 끌어다 놓으면 바로 요약
echo                         (더블클릭하면 파일 경로를 물어봅니다)
echo      kakaosum-gui.exe   창으로 쓰는 버전
echo   ============================================================
echo.
echo   동작을 한 번 확인해 봅니다...
echo.
dist\kakaosum.exe summarize samples\sample_android.txt -f text --group none
echo.
start "" "%CD%\dist"
pause
exit /b 0

:error_log
echo.
echo   [!] 실행파일을 만들지 못했습니다. build-log.txt 의 마지막 부분입니다:
echo.
powershell -NoProfile -Command "Get-Content build-log.txt -Tail 20"
echo.
pause
exit /b 1

:error
echo.
echo   [!] 준비 단계에서 실패했습니다. 위 메시지를 확인해 주세요.
echo       인터넷 연결(회사망 프록시 등)을 먼저 확인해 보세요.
echo.
pause
exit /b 1
