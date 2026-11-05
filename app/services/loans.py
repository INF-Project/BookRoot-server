from fastapi import HTTPException

from app.schemas.loans import Availability


def yes_no(value):
    if value == "Y":
        return True
    if value == "N":
        return False
    return None


class LoansService:
    def __init__(self, api):
        self.api = api

    async def availability(self, isbn13, library_code):
        body = await self.api.request("bookExist", isbn13=isbn13, libCode=library_code)
        result = body.get("result")
        if not isinstance(result, dict):
            raise HTTPException(502, "대출 상태 응답 형식이 올바르지 않습니다.")
        has_book = yes_no(result.get("hasBook"))
        available = yes_no(result.get("loanAvailable"))
        if has_book is False and available is True:
            available = None  # 모순되는 외부 데이터는 대출 가능으로 단정하지 않습니다.
        return Availability(
            isbn13=isbn13, library_code=library_code, has_book=has_book,
            loan_available=available, due_date=None, remaining_days=None,
        )
