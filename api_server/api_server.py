import sys
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import API_SERVER_PORT

app = FastAPI(title="Backend API Server")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api_server", "port": API_SERVER_PORT}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle_api(path: str, request: Request):
    now = datetime.now().strftime("%H:%M:%S")
    user_id = request.headers.get("X-User-Id", "(IP Fallback)")
    print(f"[{now}] [API-SERVER {API_SERVER_PORT}] 요청 수신 -> /{path} | user={user_id}", flush=True)

    return {
        "message": "정상 응답입니다 (API Server 처리 완료)",
        "path": f"/api/{path}",
        "user_id": user_id,
        "server_time": now,
    }