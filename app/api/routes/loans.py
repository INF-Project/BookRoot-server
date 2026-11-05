from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.schemas.loans import Availability
from app.services.books import require_isbn

router = APIRouter(prefix="/books", tags=["loans"])


@router.get("/{isbn13}/availability", response_model=Availability, summary="도서관별 대출 가능 상태")
async def availability(
    request: Request, isbn13: str,
    library_code: Annotated[str, Query(pattern=r"^[0-9]{1,20}$")],
):
    require_isbn(isbn13)
    return await request.app.state.loans.availability(isbn13, library_code)
