"""공동 클라이언트: 정보나루 통신과 응답 검증을 담당합니다."""

import asyncio
from dataclasses import dataclass

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
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self.client = client
        self.api_key = api_key
        self._requests = asyncio.Semaphore(5)
        self._book_pages = TTLCache(max_size=128)
        self._library_counts = TTLCache(max_size=2048)

    async def request(self, endpoint: str, **params):
        """정해진 정보나루 호스트를 호출합니다. 인증키를 포함한 오류는 노출하지 않습니다."""
        if not self.api_key:
            raise HTTPException(503, ".env에 DATA4LIBRARY_API_KEY를 설정하고 서버를 재시작하세요.")
        try:
            async with self._requests:
                response = await self.client.get(
                    f"https://data4library.kr/api/{endpoint}",
                    params={**params, "authKey": self.api_key, "format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "도서관 API 응답 시간이 초과되었습니다.") from None
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "도서관 API 요청에 실패했습니다. 잠시 후 다시 시도하세요.") from None
        body = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(body, dict) or body.get("error") or payload.get("error"):
            raise HTTPException(502, "도서관 API가 요청을 처리하지 못했습니다. 인증키와 이용 조건을 확인하세요.")
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
