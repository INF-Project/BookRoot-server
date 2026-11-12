"""검색 DB 또는 정보나루에서 지역별 소장 도서관을 조회합니다."""

import asyncio
import math
import sqlite3

from fastapi import HTTPException

from app.clients.data4library import response_count
from app.schemas.libraries import DISTRICT_CODES, Library, LibraryList
from app.services.distance import distance_km


def _text(value):
    return value.strip() or None if isinstance(value, str) else None


def _coordinate(value, limit):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and abs(number) <= limit else None


def _library_row(raw, district):
    if not isinstance(raw, dict) or not isinstance(raw.get("lib"), dict):
        raise HTTPException(502, "도서관 응답 형식을 확인할 수 없습니다.")
    library = raw["lib"]
    code, name = library.get("libCode"), _text(library.get("libName"))
    if (not isinstance(code, (str, int)) or isinstance(code, bool)
            or not str(code).strip() or name is None):
        raise HTTPException(502, "도서관 응답 형식을 확인할 수 없습니다.")
    address = _text(library.get("address"))
    if address and "대전" not in address:
        raise HTTPException(502, "도서관 API의 지역 응답을 확인할 수 없습니다.")
    found_district = next((name for name in DISTRICT_CODES if name in (address or "")), None)
    if district and found_district and found_district != district:
        raise HTTPException(502, "도서관 API의 지역 응답을 확인할 수 없습니다.")
    latitude = _coordinate(library.get("latitude"), 90)
    longitude = _coordinate(library.get("longitude"), 180)
    if latitude is None or longitude is None or (latitude == 0 and longitude == 0):
        latitude = longitude = None
    return {
        "library_code": str(code).strip(), "name": name, "address": address,
        "district": found_district or district, "latitude": latitude, "longitude": longitude,
        "telephone": _text(library.get("tel")), "homepage": _text(library.get("homepage")),
        "operating_time": _text(library.get("operatingTime")), "closed": _text(library.get("closed")),
    }


async def _remote_libraries(api, isbn13, district):
    params = {"region": "25", "pageSize": 100}
    if district:
        params["dtl_region"] = DISTRICT_CODES[district]
    if isbn13:
        params["isbn"] = isbn13
    endpoint = "libSrchByBook" if isbn13 else "libSrch"
    first = await api.request(endpoint, **params, pageNo=1)
    total = response_count(first)
    items, seen = [], set()
    for page in range(1, max(1, math.ceil(total / 100)) + 1):
        body = first if page == 1 else await api.request(endpoint, **params, pageNo=page)
        rows = body.get("libs", [])
        expected = min(100, max(0, total - (page - 1) * 100))
        if response_count(body) != total or not isinstance(rows, list) or len(rows) != expected:
            raise HTTPException(502, "소장 도서관 목록을 모두 확인하지 못했습니다. 다시 시도해 주세요.")
        for raw in rows:
            row = _library_row(raw, district)
            if row["library_code"] not in seen:
                seen.add(row["library_code"])
                items.append(row)
    return items


async def list_libraries(api, *, catalog_loader=None, isbn13=None, district=None,
                         latitude=None, longitude=None):
    try:
        async with asyncio.timeout(30):
            if catalog_loader is not None:
                rows = await asyncio.to_thread(lambda: catalog_loader().libraries(district, isbn13))
            else:
                rows = await _remote_libraries(api, isbn13, district)
    except TimeoutError:
        raise HTTPException(504, "도서관 목록 확인 시간이 초과되었습니다.") from None
    except (sqlite3.Error, OSError):
        raise HTTPException(503, "장서 검색 DB에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    items = []
    for raw in rows:
        row = dict(raw)
        row["distance_km"] = (distance_km(latitude, longitude, row.get("latitude"), row.get("longitude"))
                              if latitude is not None else None)
        items.append(Library(**row))
    items.sort(key=lambda row: (row.distance_km is None, row.distance_km or 0, row.name, row.library_code))
    return LibraryList(items=items, total=len(items))
