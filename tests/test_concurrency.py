import asyncio
import sys
import uuid
from pathlib import Path
import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import HTTP_TIMEOUT_SECONDS, MIDDLEWARE_URLS, TEST_TOTAL_REQUESTS

TARGET_URLS = [f"{url}/api/hello" for url in MIDDLEWARE_URLS]


async def send_one(client: httpx.AsyncClient, url: str, user_id: str) -> dict:
    resp = await client.get(url, headers={"X-User-Id": user_id})
    return {
        "status": resp.status_code,
        "limit": int(resp.headers.get("X-Ratelimit-Limit", "0")),
        "remaining": resp.headers.get("X-Ratelimit-Remaining", "-"),
        "served_by": resp.headers.get("X-Served-By", "unknown"),
    }


async def run_test() -> int:
    test_user = f"concurrency-{uuid.uuid4().hex[:8]}"
    print(
        f"[동시성 테스트 시작] 대상 노드: {MIDDLEWARE_URLS} | "
        f"총 동시 요청: {TEST_TOTAL_REQUESTS}회 | user={test_user}"
    )

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            tasks = [
                send_one(client, TARGET_URLS[i % len(TARGET_URLS)], test_user)
                for i in range(TEST_TOTAL_REQUESTS)
            ]
            results = await asyncio.gather(*tasks)
    except httpx.ConnectError:
        print(f"[실패] 미들웨어({MIDDLEWARE_URLS})에 연결할 수 없습니다. 먼저 start_all.bat을 실행해 주세요.")
        return 1

    allowed_count = sum(1 for r in results if r["status"] == 200)
    blocked_count = sum(1 for r in results if r["status"] == 429)
    detected_limit = results[0]["limit"]

    node_counts: dict[str, int] = {}
    for r in results:
        node_counts[r["served_by"]] = node_counts.get(r["served_by"], 0) + 1

    print(f" - 적용된 한도(X-Ratelimit-Limit): {detected_limit}회")
    print(f" - 허용(200 OK): {allowed_count}회 | 차단(429): {blocked_count}회")
    print(f" - 노드별 분산 처리 횟수: {node_counts}")

    expected_allowed = min(detected_limit, TEST_TOTAL_REQUESTS)
    expected_blocked = TEST_TOTAL_REQUESTS - expected_allowed

    if allowed_count == expected_allowed and blocked_count == expected_blocked and len(node_counts) == len(MIDDLEWARE_URLS):
        print("[성공] 분산 환경 동시 요청에서도 경쟁 조건 없이 정확한 한도 제한이 검증되었습니다.")
        return 0

    print(
        f"[실패] 기대값(허용={expected_allowed}, 차단={expected_blocked}, {len(MIDDLEWARE_URLS)}개 노드 분산)과 다릅니다."
    )
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_test()))