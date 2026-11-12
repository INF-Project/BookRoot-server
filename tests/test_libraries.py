from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.libraries import DISTRICT_CODES
from app.services.catalog import CatalogStore
from app.services.distance import distance_km


ISBN = "0012345678901"


@pytest.fixture
def catalog(tmp_path):
    store = CatalogStore(tmp_path / "libraries.sqlite3")
    rows = [{"library_code": f"00{index:03}", "name": f"{district} 도서관", "district": district,
             "address": f"대전광역시 {district} 테스트로", "latitude": 36.45, "longitude": 127.38}
            for index, district in enumerate(DISTRICT_CODES, 1)]
    rows[0]["latitude"] = rows[0]["longitude"] = None
    rows += [{"library_code": "00999", "name": "가까운 도서관", "district": "유성구",
              "address": "대전광역시 유성구 테스트로", "latitude": 36.35, "longitude": 127.38,
              "telephone": "042-000-0000", "homepage": "https://example.org/",
              "operating_time": "09:00~18:00", "closed": "월요일"}]
    store.replace_manifest(rows)
    for row in rows:
        books = [{"isbn13": ISBN, "bookname": "테스트 도서"}] if row["district"] == "유성구" else []
        store.replace_library(row["library_code"], books)
    yield store
    store.close()


@contextmanager
def catalog_client(catalog):
    def unexpected_request(request):
        pytest.fail("카탈로그 도서관 조회가 외부 API를 요청했습니다.")
    app = create_app(Settings(catalog_path=catalog.path), httpx.MockTransport(unexpected_request))
    with TestClient(app) as client:
        try:
            yield client
        finally:
            if app.state.books._catalog is not None:
                app.state.books._catalog.close()


def test_catalog_lists_metadata_scope_and_name_order_without_api_key(catalog):
    with catalog_client(catalog) as client:
        response = client.get("/api/libraries")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 6
        assert all(row["distance_km"] is None for row in body["items"])
        assert [row["name"] for row in body["items"]] == sorted(row["name"] for row in body["items"])
        filtered = client.get("/api/libraries", params={"district": "유성구"}).json()
        assert filtered["total"] == 2 and all(row["district"] == "유성구" for row in filtered["items"])
        row = next(row for row in body["items"] if row["library_code"] == "00999")
        assert row["telephone"] == "042-000-0000" and row["operating_time"] == "09:00~18:00"
        assert row["homepage"] == "https://example.org/" and row["closed"] == "월요일"


def test_book_holdings_preserve_string_ids_and_filter_before_distance_sort(catalog):
    with catalog_client(catalog) as client:
        body = client.get(f"/api/libraries/by-book/{ISBN}", params={
            "district": "유성구", "latitude": 36.35, "longitude": 127.38}).json()
        assert body["total"] == 2
        assert body["items"][0]["library_code"] == "00999"
        assert body["items"][0]["distance_km"] == 0
        assert 11 < body["items"][1]["distance_km"] < 12
        assert client.get(f"/api/libraries/by-book/{ISBN}", params={"district": "서구"}).json() == {"items": [], "total": 0}
        assert client.get("/api/libraries/by-book/9789999999999").json() == {"items": [], "total": 0}


def test_missing_coordinates_are_sorted_after_known_distances(catalog):
    with catalog_client(catalog) as client:
        body = client.get("/api/libraries", params={"latitude": 36.35, "longitude": 127.38}).json()
        assert body["items"][0]["distance_km"] == 0
        assert body["items"][-1]["district"] == "동구"
        assert body["items"][-1]["distance_km"] is None


@pytest.mark.parametrize("params", [
    {"latitude": 36.35}, {"longitude": 127.38}, {"latitude": "nan", "longitude": 127},
    {"latitude": 36, "longitude": "inf"}, {"latitude": 91, "longitude": 127},
    {"latitude": 36, "longitude": -181}, {"district": "강남구"},
])
def test_invalid_coordinates_or_district_are_422(catalog, params):
    with catalog_client(catalog) as client:
        for path in ["/api/libraries", f"/api/libraries/by-book/{ISBN}"]:
            result = client.get(path, params=params)
            assert result.status_code == 422 and "detail" in result.json()


@pytest.mark.parametrize("isbn", ["123", "978abcdefghij", "978-000000000", "１２３４５６７８９０１２３"])
def test_invalid_book_isbn_is_422(catalog, isbn):
    with catalog_client(catalog) as client:
        assert client.get(f"/api/libraries/by-book/{isbn}").status_code == 422


def test_incomplete_catalog_is_not_an_empty_success(tmp_path):
    store = CatalogStore(tmp_path / "empty.sqlite3")
    try:
        with catalog_client(store) as client:
            result = client.get("/api/libraries")
            assert result.status_code == 503 and "detail" in result.json()
    finally:
        store.close()


def remote_row(code="00123", **fields):
    return {"lib": {"libCode": code, "libName": f"도서관 {code}",
                    "address": "대전광역시 유성구 테스트로", "latitude": "36.35", "longitude": "127.38", **fields}}


def test_remote_pages_and_duplicates_use_complete_result_and_shared_cache():
    requests = []
    rows = [remote_row(f"{index:05}") for index in range(100)] + [remote_row("00000")]
    def handler(request):
        requests.append(request)
        params = request.url.params
        assert request.url.path.endswith("libSrchByBook")
        assert params["region"] == "25" and params["dtl_region"] == "25040"
        assert params["isbn"] == ISBN and params["authKey"] == "test-secret"
        start = (int(params["pageNo"]) - 1) * 100
        return httpx.Response(200, json={"response": {"numFound": len(rows), "libs": rows[start:start + 100]}})
    with TestClient(create_app(Settings(api_key="test-secret", search_backend="remote"), httpx.MockTransport(handler))) as client:
        params = {"district": "유성구", "latitude": 36.35, "longitude": 127.38}
        first = client.get(f"/api/libraries/by-book/{ISBN}", params=params)
        again = client.get(f"/api/libraries/by-book/{ISBN}", params=params)
        assert first.status_code == 200 and first.json() == again.json()
        assert first.json()["total"] == 100 and first.json()["items"][0]["library_code"] == "00000"
        assert len(requests) == 2


@pytest.mark.parametrize("body", [
    {"numFound": 1, "libs": []}, {"numFound": 1, "libs": [{}]},
    {"numFound": 1, "libs": [remote_row(address="서울특별시 강남구")]},
    {"numFound": 1, "libs": [remote_row(address="대전광역시 서구 테스트로")]},
    {"numFound": 1, "libs": [remote_row(libCode=True)]},
    {"numFound": "?", "libs": []},
])
def test_remote_malformed_or_wrong_region_never_becomes_empty_result(body):
    handler = lambda request: httpx.Response(200, json={"response": body})
    with TestClient(create_app(Settings(api_key="test-secret", search_backend="remote"), httpx.MockTransport(handler))) as client:
        result = client.get("/api/libraries", params={"district": "유성구"})
        assert result.status_code == 502 and "detail" in result.json()
        assert "test-secret" not in result.text


def test_remote_missing_coordinate_pair_is_null_and_optional_fields_are_preserved():
    body = {"numFound": 1, "libs": [remote_row(latitude="nan", tel="042-000-0000", closed="월요일")]}
    handler = lambda request: httpx.Response(200, json={"response": body})
    with TestClient(create_app(Settings(api_key="test-secret", search_backend="remote"), httpx.MockTransport(handler))) as client:
        row = client.get("/api/libraries", params={"latitude": 36.35, "longitude": 127.38}).json()["items"][0]
        assert row["latitude"] is row["longitude"] is row["distance_km"] is None
        assert row["telephone"] == "042-000-0000" and row["closed"] == "월요일"


def test_remote_timeout_preserves_504_without_key_in_error():
    def handler(request):
        raise httpx.ReadTimeout("https://example.org/?authKey=test-secret")
    with TestClient(create_app(Settings(api_key="test-secret", search_backend="remote"), httpx.MockTransport(handler))) as client:
        result = client.get("/api/libraries")
        assert result.status_code == 504 and "test-secret" not in result.text


def test_distance_km_returns_known_great_circle_distance_and_missing_value():
    assert distance_km(0, 0, 0, 0) == 0
    assert 111.19 < distance_km(0, 0, 0, 1) < 111.20
    assert distance_km(36, 127, None, 127) is None
