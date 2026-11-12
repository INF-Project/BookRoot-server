import math
import re
import time
from app.clients.data4library import LibraryAPIError, request_json
from app.schemas.libraries import Library, LibraryList, District
from app.services.distance import distance_km

DISTRICTS = ("동구", "중구", "서구", "유성구", "대덕구")

def coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0):
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None, None

def normalize(raw: dict) -> Library:
    code, name = raw.get("libCode"), raw.get("libName")
    if not isinstance(code, str) or not code.strip() or not isinstance(name, str) or not name.strip():
        raise LibraryAPIError("정보나루 도서관 식별 정보가 올바르지 않습니다.")
    address = raw.get("address") or ""
    if not isinstance(address, str):
        raise LibraryAPIError("정보나루 주소 정보가 올바르지 않습니다.")
    match = re.search(r"(?:^|\s)(동구|중구|서구|유성구|대덕구)(?=\s|$)", address)
    lat, lon = coordinates(raw.get("latitude"), raw.get("longitude"))
    return Library(library_code=code, name=name, address=address, district=match.group(1) if match else None,
                   latitude=lat, longitude=lon, phone=str(raw.get("tel") or ""))

def fetch_libraries(isbn13: str | None = None) -> list[Library]:
    endpoint = "libSrchByBook" if isbn13 else "libSrch"
    params = {"region": "25", "pageSize": 100}
    if isbn13:
        params["isbn"] = isbn13
    found = {}
    deadline = time.monotonic() + 30
    for page in range(1, 101):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LibraryAPIError("도서관 전체 조회 시간이 초과되었습니다.", 504)
        body = request_json(endpoint, {**params, "pageNo": page}, timeout=min(15, remaining))
        try:
            total = int(body["numFound"])
            rows = body["libs"]
            if total < 0 or not isinstance(rows, list):
                raise ValueError()
            for item in rows:
                lib = normalize(item["lib"])
                found[lib.library_code] = lib
        except (ValueError, KeyError, TypeError, AttributeError):
            raise LibraryAPIError("정보나루 도서관 목록 형식이 올바르지 않습니다.") from None
        if len(found) >= total:
            return list(found.values())
        if not rows:
            raise LibraryAPIError("정보나루 도서관 목록을 끝까지 받지 못했습니다.")
    raise LibraryAPIError("정보나루 조회 페이지 한도를 초과했습니다.")

def select_libraries(items: list[Library], district: District | None = None,
                     latitude: float | None = None, longitude: float | None = None) -> LibraryList:
    selected = []
    for original in items:
        if district and original.district != district:
            continue
        item = original.model_copy(update={"distance_km": None})
        if latitude is not None and longitude is not None and item.latitude is not None and item.longitude is not None:
            item.distance_km = distance_km(latitude, longitude, item.latitude, item.longitude)
        selected.append(item)
    selected.sort(key=lambda item: (item.distance_km is None, item.distance_km or 0, item.name, item.library_code))
    return LibraryList(items=selected, total=len(selected))
