import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import (
    API_SERVER_PORT,
    API_SERVER_URL,
    HTTP_TIMEOUT_SECONDS,
    MIDDLEWARE_1_PORT,
    REDIS_HOST,
    REDIS_PORT,
)

LUA_SCRIPT_PATH = BASE_DIR / "sliding_window_log.lua"

NODE_ID = os.getenv("NODE_ID", f"middleware-1 ({MIDDLEWARE_1_PORT})").replace('"', "").strip()
REDIS_RULES_KEY = "rate_limit:rules"
DEFAULT_RULES = {"window_seconds": 10, "limit": 5}

HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


def log(msg: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{NODE_ID}] {msg}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    lua_script_source = LUA_SCRIPT_PATH.read_text(encoding="utf-8")
    log(f"Lua 스크립트 로드 완료: {LUA_SCRIPT_PATH}")

    app.state.redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    app.state.lua_script = app.state.redis.register_script(lua_script_source)
    app.state.http_client = httpx.AsyncClient(base_url=API_SERVER_URL, timeout=HTTP_TIMEOUT_SECONDS)
    log(f"미들웨어 프록시 서버 기동 완료 (노드: {NODE_ID} -> {API_SERVER_URL} | Redis: {REDIS_HOST}:{REDIS_PORT})")
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.aclose()


app = FastAPI(title="Rate Limiter Middleware Proxy", lifespan=lifespan)


async def get_current_rules(redis_client: aioredis.Redis) -> dict:
    raw = await redis_client.get(REDIS_RULES_KEY)
    if not raw:
        return DEFAULT_RULES
    try:
        parsed = json.loads(raw)
        return {
            "window_seconds": max(1, int(parsed.get("window_seconds", 10))),
            "limit": max(1, int(parsed.get("limit", 5))),
        }
    except (ValueError, TypeError):
        return DEFAULT_RULES


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # CORS Preflight(OPTIONS) 및 헬스체크는 카운팅에서 제외
    if request.method == "OPTIONS" or request.url.path == "/health":
        return await call_next(request)

    # 클라이언트 식별자: X-User-Id 헤더 우선, 없으면 클라이언트 IP 폴백
    user_header = request.headers.get("X-User-Id", "").strip()
    client_ip = request.client.host if request.client else "unknown"
    client_id = user_header if user_header else f"ip:{client_ip}"

    try:
        rules = await get_current_rules(app.state.redis)
        window_seconds = rules["window_seconds"]
        limit = rules["limit"]
        window_ms = window_seconds * 1000
        req_id = uuid.uuid4().hex[:12]

        counter_key = f"rate_limit:sw:{client_id}"
        allowed, current_count, retry_after = await app.state.lua_script(
            keys=[counter_key],
            args=[limit, window_ms, req_id],
        )
    except aioredis.RedisError as e:
        log(f"Redis 오류 발생: {e}")
        return JSONResponse(
            status_code=503,
            content={"detail": f"Redis({REDIS_HOST}:{REDIS_PORT}) 캐시 서버에 연결할 수 없습니다."},
            headers={"X-Served-By": NODE_ID},
        )

    remaining = max(0, limit - int(current_count))
    retry_after_val = 0 if int(allowed) == 1 else max(1, int(retry_after))

    rl_headers = {
        "X-Ratelimit-Limit": str(limit),
        "X-Ratelimit-Remaining": str(remaining),
        "X-Ratelimit-Retry-After": str(retry_after_val),
        "X-Served-By": NODE_ID,
    }

    if int(allowed) == 0:
        log(
            f"[BLOCKED 429] client={client_id} | count={current_count}/{limit} "
            f"| window={window_seconds}s | retry_after={retry_after_val}s"
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too Many Requests - 요청 한도를 초과했습니다.",
                "client_id": client_id,
                "limit": limit,
                "retry_after_seconds": retry_after_val,
                "served_by": NODE_ID,
            },
            headers=rl_headers,
        )

    log(
        f"[ALLOWED 200] client={client_id} | count={current_count}/{limit} "
        f"| remaining={remaining} | window={window_seconds}s"
    )
    response = await call_next(request)
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response


# 중요: rate_limit_middleware 정의 후에 CORSMiddleware를 등록해야
# CORS가 가장 바깥쪽 레이어가 되어 429 응답에도 Expose-Headers가 정상 적용됩니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Ratelimit-Limit",
        "X-Ratelimit-Remaining",
        "X-Ratelimit-Retry-After",
        "X-Served-By",
    ],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "middleware", "node_id": NODE_ID}


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_to_api_server(full_path: str, request: Request):
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }
    body = await request.body()

    try:
        upstream_resp = await app.state.http_client.request(
            method=request.method,
            url=f"/{full_path}",
            params=request.query_params,
            headers=forward_headers,
            content=body,
        )
    except httpx.RequestError as e:
        log(f"API 서버 연결 실패 ({API_SERVER_URL}): {e}")
        return JSONResponse(
            status_code=502,
            content={"detail": f"백엔드 API 서버(Port {API_SERVER_PORT})에 연결할 수 없습니다."},
        )

    resp_headers = {
        k: v
        for k, v in upstream_resp.headers.items()
        if k.lower() not in HOP_BY_HOP_HEADERS
    }
    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type"),
    )