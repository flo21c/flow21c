@echo off
chcp 65001 > nul
setlocal
rem  윈도우에서 실행파일 만들기 - 이 파일을 더블클릭하거나 명령창에서 실행하세요.
cd /d "%~dp0.."

echo [1/3] 빌드 도구 준비
python -m pip install --upgrade pip pyinstaller || goto :error
echo [2/3] kakaosum 설치
python -m pip install . || goto :error
echo [3/3] 실행파일 만들기
python -m PyInstaller --noconfirm --clean packaging/kakaosum.spec || goto :error

echo.
echo 완성됐습니다. dist 폴더를 확인하세요.
echo   dist\kakaosum.exe      명령줄용 (대화 .txt 를 이 파일 위로 끌어다 놓으면 바로 요약)
echo   dist\kakaosum-gui.exe  창으로 쓰는 버전
pause
exit /b 0

:error
echo.
echo 빌드에 실패했습니다. 위 메시지를 확인해 주세요.
pause
exit /b 1
