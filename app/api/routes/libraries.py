from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from app.clients.data4library import LibraryAPIError
from app.schemas.libraries import District, LibraryList
from app.services.libraries import fetch_libraries, select_libraries

router = APIRouter(prefix="/libraries", tags=["libraries"])

def filters(district: District | None = None,
            latitude: Annotated[float | None, Query(ge=-90, le=90, allow_inf_nan=False)] = None,
            longitude: Annotated[float | None, Query(ge=-180, le=180, allow_inf_nan=False)] = None):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "위도와 경도를 함께 입력해 주세요.")
    return dict(district=district, latitude=latitude, longitude=longitude)

def listing(isbn13, options):
    try:
        return select_libraries(fetch_libraries(isbn13), **options)
    except LibraryAPIError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None

@router.get("", response_model=LibraryList, summary="대전 도서관 목록·구 필터·직선거리순")
def libraries(options: Annotated[dict, Depends(filters)]):
    return listing(None, options)

@router.get("/by-book/{isbn13}", response_model=LibraryList, summary="ISBN별 대전 소장 도서관")
def by_book(isbn13: Annotated[str, Path(pattern=r"^[0-9]{13}$")], options: Annotated[dict, Depends(filters)]):
    return listing(isbn13, options)
