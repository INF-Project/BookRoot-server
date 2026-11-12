from pydantic import BaseModel, Field


class Book(BaseModel):
    isbn13: str
    title: str
    authors: list[str] | None = None
    publisher: str | None = None
    publication_year: str | None = None
    publication_date: str | None = None
    book_image_url: str | None = Field(None, description="표지의 원본 URL. 미제공이면 null.")


class SearchBook(Book):
    library_count: int = Field(ge=1, description="선택 구 또는 대전 전체의 소장 도서관 수. 대출 가능 권수가 아닙니다.")
    nearest_distance_km: float | None = Field(None, ge=0, description="선택 지역 내 가장 가까운 소장 도서관까지의 직선거리 km. 위치·도서관 좌표가 없으면 null.")


class BookList(BaseModel):
    items: list[SearchBook]
    total: int
    page: int
    page_size: int
