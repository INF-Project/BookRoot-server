from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.books import Book, BookList
from app.schemas.libraries import District
from app.services.books import SearchField, require_isbn

router = APIRouter(prefix="/books", tags=["books"])


@router.get("/search", response_model=BookList, summary="대전 또는 선택 구의 도서 검색")
async def search_books(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    district: District | None = None,
    field: SearchField = "title",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if set(request.query_params) - {"q", "district", "field", "page", "page_size"}:
        raise HTTPException(422, "지원하지 않는 검색 조건이 있습니다.")
    query = q.strip()
    if not query:
        raise HTTPException(422, "검색어를 입력하세요.")
    if field == "isbn13":
        require_isbn(query)
    return await request.app.state.books.search(query, field, district, page, page_size)


@router.get("/{isbn13}", response_model=Book, summary="도서 상세 조회")
async def book_detail(request: Request, isbn13: str):
    require_isbn(isbn13)
    return await request.app.state.books.detail(isbn13)
