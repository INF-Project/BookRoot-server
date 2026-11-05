from pydantic import BaseModel


class Availability(BaseModel):
    isbn13: str
    library_code: str
    has_book: bool | None
    loan_available: bool | None
    due_date: str | None = None
    remaining_days: int | None = None
