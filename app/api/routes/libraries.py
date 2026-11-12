"""대전 도서관 목록과 도서별 소장 도서관을 제공합니다."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.libraries import District, LibraryList
from app.services.books import require_isbn
from app.services.libraries import list_libraries

router = APIRouter(prefix="/libraries", tags=["libraries"])

Latitude = Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)]


async def _list(request, isbn13, district, latitude, longitude):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "위도와 경도는 함께 입력해 주세요.")
    books = request.app.state.books
    return await list_libraries(
        request.app.state.data4library,
        catalog_loader=books._get_catalog if books.settings.search_backend == "catalog" else None,
        isbn13=isbn13, district=district, latitude=latitude, longitude=longitude,
    )


@router.get("", response_model=LibraryList, summary="대전 도서관 목록·구 필터·거리순")
async def libraries(request: Request, district: District | None = None,
                    latitude: Latitude = None, longitude: Longitude = None):
    return await _list(request, None, district, latitude, longitude)


@router.get("/by-book/{isbn13}", response_model=LibraryList, summary="도서별 대전 소장 도서관")
async def libraries_by_book(request: Request, isbn13: str, district: District | None = None,
                           latitude: Latitude = None, longitude: Longitude = None):
    require_isbn(isbn13)
    return await _list(request, isbn13, district, latitude, longitude)
