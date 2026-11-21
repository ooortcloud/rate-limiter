@echo off
chcp 65001 >nul
setlocal
title Start-Rate-Limiter
pushd "%~dp0"

:: 이전 비정상 종료로 남은 신호 파일 정리
if exist ".stop_signal" del /q ".stop_signal" >nul 2>&1

:: .env 미존재 시 .env.example 자동 복사
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo [준비] .env.example을 복사해 기본 .env 파일을 생성했습니다.
    )
)

:: 기본값 설정 후 .env 로드
set "REDIS_PORT=6379"
set "API_SERVER_HOST=127.0.0.1"
set "API_SERVER_PORT=8001"
set "MIDDLEWARE_HOST=127.0.0.1"
set "MIDDLEWARE_1_PORT=8000"
set "MIDDLEWARE_2_PORT=8002"
set "CLIENT_HOST=127.0.0.1"
set "CLIENT_PORT=3000"

if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

echo ==================================================
echo  Rate Limiter Demo - 일괄 실행 스크립트 (분산 2노드)
echo ==================================================

:: 0. 필수 프로젝트 파일 위치 확인
for %%f in ("config.py" "api_server\api_server.py" "worker\worker.py" "worker\rules.json" "middleware\middleware.py" "middleware\sliding_window_log.lua" "client\server.py" "client\index.html") do (
    if not exist %%f (
        echo [오류] 필수 파일을 찾을 수 없습니다: %%~f
        echo 현재 폴더^(%CD%^)에 파일이 올바른 위치에 있는지 확인해 주세요.
        echo.
        echo [현재 폴더 내 파일 목록]
        dir /b
        pause
        popd
        exit /b 1
    )
)

:: 1. Docker 실행 여부 확인
docker info >nul 2>&1
if errorlevel 1 (
    echo [오류] Docker가 실행 중이지 않습니다. Docker Desktop을 먼저 실행해 주세요.
    pause
    popd
    exit /b 1
)

:: 2. Python 가상환경(.venv) 확인 및 패키지 자동 동기화
if not exist ".venv\Scripts\python.exe" (
    echo [준비] .venv 가상환경이 없어 새로 생성하고 패키지를 설치합니다...
    python -m venv .venv
    if errorlevel 1 (
        echo [오류] Python 가상환경 생성에 실패했습니다. Python 설치를 확인해 주세요.
        pause
        popd
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] requirements.txt 설치에 실패했습니다.
        pause
        popd
        exit /b 1
    )
) else (
    echo [확인] 기존 .venv 가상환경을 사용합니다.
    ".venv\Scripts\python.exe" -c "import dotenv" >nul 2>&1
    if errorlevel 1 (
        echo [준비] 신규 의존성^(python-dotenv^)을 설치합니다...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [오류] requirements.txt 설치에 실패했습니다.
            pause
            popd
            exit /b 1
        )
    )
)

:: 3. Redis 컨테이너 기동 및 준비 대기
echo [1/6] Redis Docker 컨테이너 기동 중 (Port %REDIS_PORT%)...
docker compose up -d
if errorlevel 1 (
    echo [오류] docker compose up -d 실행에 실패했습니다.
    pause
    popd
    exit /b 1
)

echo [대기] Redis 응답(PONG) 확인 중...
set /a RETRY=0
:WAIT_REDIS
docker exec rate-limiter-redis redis-cli ping >nul 2>&1
if not errorlevel 1 goto REDIS_READY
set /a RETRY+=1
if %RETRY% GEQ 15 (
    echo [오류] Redis가 15초 내에 준비되지 않았습니다.
    pause
    popd
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto WAIT_REDIS

:REDIS_READY
echo [완료] Redis 준비 완료!

:: 자식 Python 프로세스 한글/UTF-8 출력 보장
set PYTHONUTF8=1

:: 4. 나머지 5개 노드를 각각 독립된 콘솔 창(conhost)으로 실행
echo [2/6] 작업 프로세스(Worker) 실행...
start "RL-Node-Worker" /D "%CD%" conhost.exe cmd /k "chcp 65001 >nul && title RL-Node-Worker && .\.venv\Scripts\python.exe -m worker.worker"

echo [3/6] API 서버(Port %API_SERVER_PORT%) 실행...
start "RL-Node-APIServer" /D "%CD%" conhost.exe cmd /k "chcp 65001 >nul && title RL-Node-APIServer && .\.venv\Scripts\python.exe -m uvicorn api_server.api_server:app --app-dir . --host %API_SERVER_HOST% --port %API_SERVER_PORT%"

echo [4/6] 처리율 제한 미들웨어 Node 1(Port %MIDDLEWARE_1_PORT%) 실행...
set "NODE_ID=middleware-1 (%MIDDLEWARE_1_PORT%)"
start "RL-Node-Middleware-1" /D "%CD%" conhost.exe cmd /k "chcp 65001 >nul && title RL-Node-Middleware-1 && .\.venv\Scripts\python.exe -m uvicorn middleware.middleware:app --app-dir . --host %MIDDLEWARE_HOST% --port %MIDDLEWARE_1_PORT%"

echo [5/6] 처리율 제한 미들웨어 Node 2(Port %MIDDLEWARE_2_PORT%) 실행...
set "NODE_ID=middleware-2 (%MIDDLEWARE_2_PORT%)"
start "RL-Node-Middleware-2" /D "%CD%" conhost.exe cmd /k "chcp 65001 >nul && title RL-Node-Middleware-2 && .\.venv\Scripts\python.exe -m uvicorn middleware.middleware:app --app-dir . --host %MIDDLEWARE_HOST% --port %MIDDLEWARE_2_PORT%"
set "NODE_ID="

echo [6/6] 클라이언트 서버(Port %CLIENT_PORT%) 실행...
start "RL-Node-Client" /D "%CD%" conhost.exe cmd /k "chcp 65001 >nul && title RL-Node-Client && .\.venv\Scripts\python.exe -m client.server"

:: 서버 부팅 대기 후 브라우저 자동 오픈
echo [대기] 서버 기동 대기 중 (3초)...
timeout /t 3 /nobreak >nul

echo [완료] 브라우저에서 클라이언트를 엽니다: http://%CLIENT_HOST%:%CLIENT_PORT%
start "" "http://%CLIENT_HOST%:%CLIENT_PORT%"

echo.
echo ==================================================
echo  모든 노드가 실행 중입니다. (이 창은 종료 전까지 유지됩니다)
echo  전체 종료는 stop_all.bat 을 실행하세요.
echo ==================================================

:KEEP_ALIVE
if exist ".stop_signal" (
    del /q ".stop_signal" >nul 2>&1
    popd
    endlocal
    exit /b 0
)
timeout /t 1 /nobreak >nul
goto KEEP_ALIVE