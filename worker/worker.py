import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import redis

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import REDIS_HOST, REDIS_PORT

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")
REDIS_RULES_KEY = "rate_limit:rules"


def log(msg: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [WORKER] {msg}", flush=True)


def load_rules_from_disk() -> dict:
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    window_seconds = max(1, int(data.get("window_seconds", 10)))
    limit = max(1, int(data.get("limit", 5)))
    sync_interval = max(1, int(data.get("sync_interval_seconds", 3)))

    return {
        "window_seconds": window_seconds,
        "limit": limit,
        "sync_interval_seconds": sync_interval,
    }


def main() -> None:
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    last_synced_payload = None
    sync_interval = 3

    log(f"규칙 동기화 워커 시작 (Redis: {REDIS_HOST}:{REDIS_PORT} | 감시 파일: {RULES_FILE})")

    while True:
        try:
            rules = load_rules_from_disk()
            sync_interval = rules["sync_interval_seconds"]
            payload = json.dumps(
                {
                    "window_seconds": rules["window_seconds"],
                    "limit": rules["limit"],
                }
            )

            if payload != last_synced_payload:
                client.set(REDIS_RULES_KEY, payload)
                last_synced_payload = payload
                log(
                    f"Redis 규칙 반영 완료 -> window={rules['window_seconds']}초, "
                    f"limit={rules['limit']}회 (다음 확인: {sync_interval}초 후)"
                )
            else:
                # 최초 동기화 이후 변경 없을 때도 주기 동작 확인용 로그
                log(
                    f"규칙 변경 없음 (현재: window={rules['window_seconds']}초, "
                    f"limit={rules['limit']}회)"
                )

        except FileNotFoundError:
            log(f"오류: 설정 파일을 찾을 수 없습니다 ({RULES_FILE})")
        except json.JSONDecodeError as e:
            log(f"오류: rules.json 파싱 실패 ({e})")
        except redis.RedisError as e:
            log(f"오류: Redis({REDIS_HOST}:{REDIS_PORT}) 연결 실패 - Docker 상태를 확인하세요 ({e})")
            last_synced_payload = None  # 재연결 시 강제 재동기화

        time.sleep(sync_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("워커 프로세스를 종료합니다.")