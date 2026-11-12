from typing import Literal
from pydantic import BaseModel

District = Literal["동구", "중구", "서구", "유성구", "대덕구"]

class Library(BaseModel):
    library_code: str
    name: str
    address: str
    district: District | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    phone: str = ""

class LibraryList(BaseModel):
    items: list[Library]
    total: int
