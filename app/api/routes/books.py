from typing import Annotated, Literal

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
    sort: Literal["relevance", "distance"] = "relevance",
    latitude: Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)] = None,
):
    if set(request.query_params) - {"q", "district", "field", "page", "page_size", "sort", "latitude", "longitude"}:
        raise HTTPException(422, "지원하지 않는 검색 조건이 있습니다.")
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "위도와 경도는 함께 입력해 주세요.")
    if sort == "distance" and latitude is None:
        raise HTTPException(422, "가까운 순으로 검색하려면 내 위치를 먼저 확인해 주세요.")
    query = q.strip()
    if not query:
        raise HTTPException(422, "검색어를 입력하세요.")
    if field == "isbn13":
        require_isbn(query)
    return await request.app.state.books.search(query, field, district, page, page_size,
        sort=sort, latitude=latitude, longitude=longitude)


@router.get("/{isbn13}", response_model=Book, summary="도서 상세 조회")
async def book_detail(request: Request, isbn13: str):
    require_isbn(isbn13)
    return await request.app.state.books.detail(isbn13)
