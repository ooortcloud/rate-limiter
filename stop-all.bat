@echo off
chcp 65001 >nul
setlocal
title Stop-Rate-Limiter
pushd "%~dp0"

:: 기본값 설정 후 .env 로드 (커스텀 포트까지 정확히 정리하기 위함)
set "API_SERVER_PORT=8001"
set "MIDDLEWARE_1_PORT=8000"
set "MIDDLEWARE_2_PORT=8002"
set "CLIENT_PORT=3000"

if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

echo ==================================================
echo  Rate Limiter Demo - 일괄 종료 스크립트
echo ==================================================

:: 0. start_all.bat 창에 정상 종료 신호 전송
type nul > ".stop_signal"

:: 1. 실행된 모든 노드 콘솔(cmd.exe) 및 하위 프로세스 트리 일괄 종료 (Windows 11 호환)
echo [1/4] 실행 중인 노드 창(Worker, API, Middleware 1/2, Client) 종료 중...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*RL-Node-*' } | ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null }"
taskkill /F /T /FI "WINDOWTITLE eq RL-Node-*" >nul 2>&1

:: 2. 설정된 포트(.env 기준) 잔여 프로세스 확인 및 정리
echo [2/4] 포트(%MIDDLEWARE_1_PORT%, %API_SERVER_PORT%, %MIDDLEWARE_2_PORT%, %CLIENT_PORT%) 잔여 프로세스 정리 중...
for %%p in (%MIDDLEWARE_1_PORT% %API_SERVER_PORT% %MIDDLEWARE_2_PORT% %CLIENT_PORT%) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        if not "%%a"=="0" taskkill /F /PID %%a >nul 2>&1
    )
)

:: 3. Redis Docker 컨테이너 중지 및 제거
echo [3/4] Redis Docker 컨테이너 종료 중...
docker compose down

:: 4. start_all.bat 창 종료 확인 및 잔여 정리
echo [4/4] 시작 스크립트(start_all.bat) 창 정리 중...
timeout /t 2 /nobreak >nul
if exist ".stop_signal" del /q ".stop_signal" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*start_all.bat*' } | ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null }"

echo.
echo [완료] 모든 콘솔 창과 컨테이너가 정리되었습니다.
popd
endlocal
exit /b 0