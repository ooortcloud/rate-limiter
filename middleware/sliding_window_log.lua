-- 이동 윈도 로그(Sliding Window Log) 원자적 Lua Script
-- KEYS[1]: rate_limit:sw:{client_id}
-- ARGV[1]: limit (윈도당 최대 요청 수)
-- ARGV[2]: window_ms (윈도 크기, 밀리초)
-- ARGV[3]: req_id (동일 밀리초 내 Member 중복 방지용 고유 ID)
-- 반환값: {allowed (1 or 0), current_count, retry_after_sec}

local t = redis.call("TIME")
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local req_id = ARGV[3]
local cutoff = now_ms - window_ms

-- 1. 현재 시점 기준 윈도 밖으로 벗어난 만료 로그 제거
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", cutoff)

-- 2. 현재 윈도 내 유효 요청 수 확인
local current_count = tonumber(redis.call("ZCARD", KEYS[1]))

-- 3. 한도 초과 시 차단 (차단된 요청은 ZADD 하지 않음)
if current_count >= limit then
    local oldest = redis.call("ZRANGE", KEYS[1], 0, 0, "WITHSCORES")
    local retry_after_sec = 1
    if #oldest >= 2 then
        local oldest_ms = tonumber(oldest[2])
        local wait_ms = (oldest_ms + window_ms) - now_ms
        if wait_ms > 0 then
            retry_after_sec = math.ceil(wait_ms / 1000)
        end
    end
    return {0, current_count, retry_after_sec}
end

-- 4. 허용된 요청만 고유 Member로 기록하고 키 만료 시간 갱신
local member = tostring(now_ms) .. ":" .. req_id
redis.call("ZADD", KEYS[1], now_ms, member)
redis.call("PEXPIRE", KEYS[1], window_ms)

return {1, current_count + 1, 0}