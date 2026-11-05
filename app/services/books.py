import asyncio
from math import ceil
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.clients.data4library import Data4LibraryClient
from app.core.config import Settings
from app.schemas.books import Book, BookList, SearchBook
from app.services.cache import TTLCache

SearchField = Literal["title", "author", "publisher", "keyword", "isbn13"]


def text_value(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    return str(value).strip() or None


def valid_isbn(value):
    value = text_value(value)
    return value if value and len(value) == 13 and value.isascii() and value.isdigit() else None


def require_isbn(value):
    if valid_isbn(value) is None:
        raise HTTPException(422, "ISBN에는 하이픈 없는 숫자 13자리를 입력하세요.")


def image_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def normalize_book(row, isbn13=None):
    raw = row.get("authors")
    if isinstance(raw, str):
        authors = [part.strip() for part in raw.split(";") if part.strip()] or None
    elif isinstance(raw, list):
        authors = [value.strip() for value in raw if isinstance(value, str) and value.strip()] or None
    else:
        authors = None
    return Book(
        isbn13=isbn13 or row["isbn13"], title=text_value(row.get("bookname")) or "제목 정보 없음",
        authors=authors, publisher=text_value(row.get("publisher")),
        publication_year=text_value(row.get("publication_year")),
        publication_date=text_value(row.get("publication_date")),
        book_image_url=image_url(row.get("bookImageURL")),
    )


async def gather_or_cancel(awaitables):
    tasks = [asyncio.create_task(item) for item in awaitables]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class BooksService:
    def __init__(self, api: Data4LibraryClient, settings: Settings):
        self.api, self.settings = api, settings
        self._searches = TTLCache(max_size=64)

    async def _build_regional_results(self, query, field, district):
        size = self.settings.source_page_size
        first = await self.api.search_page(query, field, 1, size)
        if first.total > self.settings.max_search_candidates:
            raise HTTPException(422, f"검색 후보가 {self.settings.max_search_candidates}건을 초과했습니다. 제목·저자 또는 ISBN으로 더 구체적으로 검색하세요.")
        pages = await gather_or_cancel(
            self.api.search_page(query, field, page, size)
            for page in range(2, ceil(first.total / size) + 1)
        )
        if any(page.total != first.total for page in pages):
            raise HTTPException(502, "검색 중 외부 데이터가 변경되었습니다. 다시 검색하세요.")
        # 지역 확인과 중복 제거를 모두 마친 후에 페이지를 나눕니다.
        unique = {}
        for page in [first, *pages]:
            for row in page.books:
                isbn = valid_isbn(row.get("isbn13"))
                if isbn is not None and isbn not in unique:
                    unique[isbn] = normalize_book(row, isbn)
        counts = await gather_or_cancel(self.api.library_count(isbn, district) for isbn in unique)
        return [SearchBook(**book.model_dump(), library_count=count)
                for book, count in zip(unique.values(), counts) if count > 0]

    async def search(self, query, field, district, page, page_size):
        key = (query, field, district)
        items = self._searches.get(key)
        if items is None:
            try:
                items = await asyncio.wait_for(
                    self._build_regional_results(query, field, district),
                    timeout=self.settings.search_timeout_seconds,
                )
            except TimeoutError:
                raise HTTPException(504, "지역별 소장 여부 확인이 지연되고 있습니다. 검색어를 구체화하거나 잠시 후 다시 시도하세요.") from None
            self._searches.put(key, items)
        start = (page - 1) * page_size
        return BookList(items=items[start:start + page_size], total=len(items), page=page, page_size=page_size)

    async def detail(self, isbn13):
        body = await self.api.request("srchDtlList", isbn13=isbn13, loaninfoYN="N")
        details = body.get("detail", [])
        if isinstance(details, dict):
            details = [details]
        if not isinstance(details, list):
            raise HTTPException(502, "도서 상세 응답 형식이 올바르지 않습니다.")
        if not details:
            raise HTTPException(404, "도서 상세 정보를 찾을 수 없습니다.")
        if not isinstance(details[0], dict) or not isinstance(details[0].get("book"), dict):
            raise HTTPException(502, "도서 상세 응답 형식이 올바르지 않습니다.")
        return normalize_book(details[0]["book"], isbn13)
