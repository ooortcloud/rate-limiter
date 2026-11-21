import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# 실행 시 주입된 OS 환경변수(예: NODE_ID)를 우선하고, 나머지 설정은 루트 .env에서 로드
load_dotenv(BASE_DIR / ".env", override=False)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

API_SERVER_HOST = os.getenv("API_SERVER_HOST", "127.0.0.1")
API_SERVER_PORT = int(os.getenv("API_SERVER_PORT", "8001"))
API_SERVER_URL = f"http://{API_SERVER_HOST}:{API_SERVER_PORT}"

MIDDLEWARE_HOST = os.getenv("MIDDLEWARE_HOST", "127.0.0.1")
MIDDLEWARE_1_PORT = int(os.getenv("MIDDLEWARE_1_PORT", "8000"))
MIDDLEWARE_2_PORT = int(os.getenv("MIDDLEWARE_2_PORT", "8002"))
MIDDLEWARE_URLS = [
    f"http://{MIDDLEWARE_HOST}:{MIDDLEWARE_1_PORT}",
    f"http://{MIDDLEWARE_HOST}:{MIDDLEWARE_2_PORT}",
]
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "5.0"))

CLIENT_HOST = os.getenv("CLIENT_HOST", "127.0.0.1")
CLIENT_PORT = int(os.getenv("CLIENT_PORT", "3000"))

TEST_TOTAL_REQUESTS = int(os.getenv("TEST_TOTAL_REQUESTS", "20"))