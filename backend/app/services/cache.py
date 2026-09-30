"""메모리 TTL 캐시. 외부 API(ECOS·FRED 등) 호출 결과를 잠시 담아둔다.

서버 재시작·재배포(Render 슬립 포함)면 캐시가 비워진다 — 그러면 다음 요청 때 다시 받아온다.
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
