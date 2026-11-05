from typing import Literal

from pydantic import BaseModel

District = Literal["동구", "중구", "서구", "유성구", "대덕구"]
DISTRICT_CODES = {"동구": "25010", "중구": "25020", "서구": "25030", "유성구": "25040", "대덕구": "25050"}


class Library(BaseModel):
    library_code: str
    name: str
    address: str | None = None
    district: District | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None


class LibraryList(BaseModel):
    items: list[Library]
    total: int
