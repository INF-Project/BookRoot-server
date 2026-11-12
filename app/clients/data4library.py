"""공동 클라이언트: 정보나루 통신과 응답 검증을 담당합니다."""

import asyncio
from dataclasses import dataclass
from time import monotonic

import httpx
from fastapi import HTTPException

from app.schemas.libraries import DISTRICT_CODES
from app.services.cache import TTLCache


@dataclass(frozen=True)
class CandidatePage:
    books: list[dict]
    total: int


def response_count(body):
    value = body.get("numFound")
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise HTTPException(502, "도서관 API의 검색 건수 형식이 올바르지 않습니다.")
    return int(value)


class Data4LibraryClient:
    def __init__(self, client: httpx.AsyncClient, api_key: str, *, clock=monotonic,
                 request_interval=0.2, retry_delay=0.25):
        self.client = client
        self.api_key = api_key
        self._requests = asyncio.Semaphore(5)
        self._book_pages = TTLCache(max_size=128)
        self._library_counts = TTLCache(max_size=2048)
        self._clock, self._interval, self._retry_delay = clock, request_interval, retry_delay
        self._pace_lock = asyncio.Lock()
        self._last_sent = 0.0
        self._flights = {}
        self._blocked_until = 0.0
        self._blocked_message = ""
        self._responses = {name: TTLCache(max_size=256, ttl=ttl, clock=clock) for name, ttl in {
            "bookExist": 60, "srchDtlList": 3600, "libSrch": 3600,
            "libSrchByBook": 600, "srchBooks": 300,
        }.items()}

    def _check_blocked(self):
        remaining = self._blocked_until - self._clock()
        if remaining > 0:
            raise HTTPException(503, self._blocked_message,
                                headers={"Retry-After": str(max(1, int(remaining + 0.999)))})

    def _limit(self, message, seconds=60):
        self._blocked_until = self._clock() + seconds
        self._blocked_message = message
        raise HTTPException(503, message, headers={"Retry-After": str(seconds)})

    def _source_error(self, error):
        # 원문에는 URL/인증키가 포함될 수 있어 고정된 안내로만 변환합니다.
        message = str(error).casefold()
        if "ip" in message and ("500" in message or "등록" in message):
            self._limit("정보나루의 일일 요청 한도에 도달했습니다. 1일 500건 이상 사용하려면 정보나루 계정에 서버의 공인 IP를 등록해야 합니다.")
        if any(word in message for word in ("quota", "rate limit", "한도", "요청 제한", "초과")):
            self._limit("정보나루의 요청 한도에 도달했습니다. 이용 한도와 서버 IP 등록 상태를 확인해 주세요.")
        if any(word in message for word in ("인증", "auth", "api key", "인증키")):
            raise HTTPException(502, "정보나루 인증키를 확인할 수 없습니다. 서버의 인증키 설정과 승인 상태를 확인해 주세요.")
        raise HTTPException(502, "정보나루가 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")

    async def _pace(self):
        if self._interval <= 0:
            return
        async with self._pace_lock:
            elapsed = monotonic() - self._last_sent
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_sent = monotonic()

    async def request(self, endpoint: str, **params):
        """정해진 정보나루 호스트를 호출합니다. 인증키를 포함한 오류는 노출하지 않습니다."""
        if not self.api_key:
            raise HTTPException(503, ".env에 DATA4LIBRARY_API_KEY를 설정하고 서버를 재시작하세요.")
        key = (endpoint, tuple(sorted((name, str(value)) for name, value in params.items())))
        cache = self._responses.get(endpoint)
        if cache is not None and (saved := cache.get(key)) is not None:
            return saved
        self._check_blocked()
        flight = self._flights.get(key)
        if flight is None:
            flight = {"task": asyncio.create_task(self._fetch(endpoint, params, cache, key)), "waiters": 0}
            self._flights[key] = flight
        flight["waiters"] += 1
        try:
            return await asyncio.shield(flight["task"])
        finally:
            flight["waiters"] -= 1
            if not flight["waiters"]:
                if not flight["task"].done():
                    flight["task"].cancel()
                    await asyncio.gather(flight["task"], return_exceptions=True)
                if self._flights.get(key) is flight:
                    del self._flights[key]

    async def _fetch(self, endpoint, params, cache, key):
        for attempt in range(2):
            try:
                async with self._requests:
                    self._check_blocked()
                    await self._pace()
                    self._check_blocked()
                    response = await self.client.get(
                        f"https://data4library.kr/api/{endpoint}",
                        params={**params, "authKey": self.api_key, "format": "json"},
                    )
                if response.status_code == 429:
                    self._limit("정보나루의 요청이 제한되었습니다. 잠시 후 다시 시도하고 이용 한도를 확인해 주세요.")
                if response.status_code >= 500 and not attempt:
                    await asyncio.sleep(self._retry_delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            except httpx.TimeoutException:
                raise HTTPException(504, "도서관 API 응답 시간이 초과되었습니다.") from None
            except (httpx.NetworkError, httpx.RemoteProtocolError):
                if not attempt:
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise HTTPException(502, "정보나루 연결에 실패했습니다. 잠시 후 다시 시도하세요.") from None
            except (httpx.HTTPError, ValueError):
                raise HTTPException(502, "도서관 API 요청에 실패했습니다. 잠시 후 다시 시도하세요.") from None
        body = payload.get("response") if isinstance(payload, dict) else None
        error = (body.get("error") if isinstance(body, dict) else None) or (payload.get("error") if isinstance(payload, dict) else None)
        if error:
            self._source_error(error)
        if not isinstance(body, dict):
            raise HTTPException(502, "정보나루 응답 형식을 확인할 수 없습니다.")
        if cache is not None:
            cache.put(key, body)
        return body

    async def search_page(self, query, field, page, page_size):
        key = (query, field, page, page_size)
        cached = self._book_pages.get(key)
        if cached is not None:
            return cached
        body = await self.request("srchBooks", **{field: query, "pageNo": page, "pageSize": page_size})
        total = response_count(body)
        rows = body.get("docs", [])
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("doc"), dict) for row in rows
        ):
            raise HTTPException(502, "도서 검색 응답 형식이 올바르지 않습니다.")
        expected = min(page_size, max(0, total - (page - 1) * page_size))
        if len(rows) != expected:
            raise HTTPException(502, "도서관 API에서 검색 후보를 모두 받지 못했습니다.")
        result = CandidatePage(books=[row["doc"] for row in rows], total=total)
        self._book_pages.put(key, result)
        return result

    async def library_count(self, isbn13, district):
        key = (isbn13, district)
        cached = self._library_counts.get(key)
        if cached is not None:
            return cached
        params = {"isbn": isbn13, "region": "25", "pageNo": 1, "pageSize": 1}
        if district is not None:
            params["dtl_region"] = DISTRICT_CODES[district]
        body = await self.request("libSrchByBook", **params)
        count = response_count(body)
        self._library_counts.put(key, count)
        return count
