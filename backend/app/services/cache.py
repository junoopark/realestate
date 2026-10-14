"""메모리 TTL 캐시 — DB 조회 결과(응답 JSON)를 잠시 담아 같은 요청을 다시 계산하지 않는다.

3단 캐시 중 가장 안쪽 층이다: 브라우저/CDN(Cache-Control·ETag) → 이 메모리 캐시 → DB(외부 API 의 영속 캐시).
서버 재시작·재배포(Render 슬립 포함)면 비워진다 — 그러면 다음 요청 때 DB 에서 다시 읽는다.
"""

import time
from typing import Callable, TypeVar

T = TypeVar("T")

_store: dict[str, tuple[float, T]] = {}


def get_or_set(key: str, ttl_seconds: int, fetch: Callable[[], T]) -> T:
    now = time.time()
    cached = _store.get(key)
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]

    try:
        value = fetch()
    except Exception:
        if cached:  # 새로 받아오지 못하면 오래된 값이라도 돌려준다
            return cached[1]
        raise

    _store[key] = (now, value)
    return value


def clear(prefix: str = "") -> int:
    """수집이 끝나면 호출 — 오래된 응답이 TTL 동안 남지 않게 한다."""
    keys = [k for k in _store if k.startswith(prefix)]
    for k in keys:
        _store.pop(k, None)
    return len(keys)
