import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.cache import TTLCache
from conftest import book, client_for, search


def test_region_filter_deduplication_and_paging_use_complete_results():
    rows = [book(1), book(1), book(2), book(3), book(4)]
    holdings = {(book(n)["isbn13"], "25040"): n for n in [1, 3, 4]}
    with client_for(rows, holdings, source_page_size=2) as (client, fake):
        first = search(client, district="유성구", page_size=2).json()
        assert first["total"] == 3 and first["page"] == 1 and first["page_size"] == 2
        assert [r["isbn13"] for r in first["items"]] == [book(1)["isbn13"], book(3)["isbn13"]]
        assert first["items"][0]["authors"] == ["저자 A", "저자 B"]
        assert first["items"][0]["book_image_url"] == "https://example.com/cover.jpg"
        assert first["items"][0]["publication_date"] is None
        count = len(fake.requests)
        second = search(client, district="유성구", page=2, page_size=2).json()
        assert second["total"] == 3 and second["items"][0]["isbn13"] == book(4)["isbn13"]
        assert len(fake.requests) == count  # 같은 지역 검색은 캐시된 결과에서 페이지를 나눕니다.
        assert search(client, district="유성구", page=3, page_size=2).json()["items"] == []


@pytest.mark.parametrize("district,code", [("동구", "25010"), ("중구", "25020"), ("서구", "25030"), ("유성구", "25040"), ("대덕구", "25050"), (None, None)])
def test_district_parameters(district, code):
    row = book(1)
    with client_for([row], {(row["isbn13"], code): 2}) as (client, fake):
        params = {"district": district} if district else {}
        assert search(client, **params).json()["items"][0]["library_count"] == 2
        request = next(r for r in fake.requests if r.url.path.endswith("libSrchByBook"))
        assert request.url.params.get("dtl_region") == code


@pytest.mark.parametrize("cover", [None, "", "javascript:alert(1)", "data:image/png;base64,x", "https://user:password@example.com/cover"])
def test_invalid_and_missing_cover_are_null(cover):
    row = book(1, bookImageURL=cover)
    with client_for([row], {(row["isbn13"], None): 1}) as (client, _):
        assert search(client).json()["items"][0]["book_image_url"] is None


def test_missing_fields_and_no_matching_district_holdings():
    with client_for([book(1)]) as (client, _):
        assert search(client).json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    row = book(1, authors=None, publisher=None, publication_year=None, bookname=None)
    with client_for([row], {(row["isbn13"], None): 1}) as (client, _):
        result = search(client).json()["items"][0]
        assert result["authors"] is None and result["publisher"] is None
        assert result["title"] == "제목 정보 없음"


@pytest.mark.parametrize("params", [{"q": " "}, {"q": "a" * 101}, {"district": "강남구"}, {"page": 0}, {"page_size": 101}, {"field": "bad"}, {"field": "isbn13", "q": "bad"}, {"cursor": "old"}])
def test_invalid_input_is_422_without_external_requests(params):
    with client_for() as (client, fake):
        result = search(client, **params)
        assert result.status_code == 422 and "detail" in result.json()
        assert fake.requests == []


def test_broad_search_is_rejected_without_fabricating_totals():
    with client_for([book(1), book(2)], max_search_candidates=1) as (client, fake):
        result = search(client)
        assert result.status_code == 422 and "구체적" in result.json()["detail"]
        assert len(fake.requests) == 1


def test_source_query_is_trimmed_and_field_is_preserved():
    with client_for() as (client, fake):
        assert search(client, q="  예제 작가  ", field="author").status_code == 200
        assert fake.requests[0].url.params["author"] == "예제 작가"


def test_detail_matches_contract_and_search_path_is_not_parsed_as_isbn():
    def handler(request):
        assert request.url.path.endswith("srchDtlList")
        return httpx.Response(200, json={"response": {"detail": [{"book": book(1, publication_date="2026-06-20")} ]}})
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        result = client.get(f"/api/books/{book(1)['isbn13']}")
        assert result.status_code == 200
        assert result.json()["publication_date"] == "2026-06-20"
        assert isinstance(result.json()["authors"], list)
        assert client.get("/api/books/bad").status_code == 422
    with client_for() as (client, _):
        assert search(client).status_code == 200


@pytest.mark.parametrize("payload,status", [({"detail": []}, 404), ({"detail": [None]}, 502), ({"detail": "bad"}, 502)])
def test_detail_missing_and_malformed(payload, status):
    handler = lambda request: httpx.Response(200, json={"response": payload})
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        assert client.get(f"/api/books/{book(1)['isbn13']}").status_code == status


def test_health_without_key_and_missing_key_error():
    with TestClient(create_app(Settings())) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert search(client).status_code == 503


@pytest.mark.parametrize("failure,expected", [("timeout", 504), ("http", 502), ("json", 502), ("api", 502), ("missing_total", 502), ("missing_rows", 502)])
def test_external_errors_have_safe_default_detail(failure, expected):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret", request=request)
        if failure == "http":
            return httpx.Response(500, text="test-secret")
        if failure == "json":
            return httpx.Response(200, text="test-secret")
        if failure == "api":
            return httpx.Response(200, json={"response": {"error": "test-secret"}})
        if failure == "missing_total":
            return httpx.Response(200, json={"response": {"docs": []}})
        return httpx.Response(200, json={"response": {"numFound": 1, "docs": []}})
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        result = search(client)
        assert result.status_code == expected and "detail" in result.json()
        assert "test-secret" not in result.text and "authKey" not in result.text


def test_regional_lookup_failure_is_not_a_false_empty_result():
    def handler(request):
        if request.url.path.endswith("srchBooks"):
            return httpx.Response(200, json={"response": {"numFound": 1, "docs": [{"doc": book(1)}]}})
        return httpx.Response(500)
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        assert search(client).status_code == 502


def test_whole_search_has_a_deadline():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"response": {"numFound": 0, "docs": []}})
    settings = Settings(api_key="test-secret", search_timeout_seconds=0.01)
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        assert search(client).status_code == 504


def test_cache_eviction_and_expiration():
    now = [0]
    cache = TTLCache(max_size=1, ttl=10, clock=lambda: now[0])
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") is None
    now[0] = 11
    assert cache.get("b") is None
