"""정보나루 오류 분류·호출 절약을 외부 통신 없이 검사합니다."""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.clients.data4library import Data4LibraryClient


ISBN = "9791161571188"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_api(client, clock=None):
    return Data4LibraryClient(
        client, "test-secret", clock=clock or Clock(),
        request_interval=0, retry_delay=0,
    )


@pytest.mark.parametrize("endpoint,params,ttl", [
    ("bookExist", {"isbn13": ISBN, "libCode": "00123"}, 60),
    ("srchDtlList", {"isbn13": ISBN}, 3600),
    ("libSrchByBook", {"isbn": ISBN, "region": "25", "dtl_region": "25040"}, 600),
    ("libSrch", {"region": "25"}, 3600),
    ("srchBooks", {"title": "테스트", "pageNo": 1, "pageSize": 50}, 300),
])
def test_success_cache_expires_at_endpoint_ttl(endpoint, params, ttl):
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"response": {"generation": calls}})

        clock = Clock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client, clock)
            first = await api.request(endpoint, **params)
            clock.now = ttl - 0.01
            assert await api.request(endpoint, **params) == first
            assert calls == 1
            clock.now = ttl
            assert await api.request(endpoint, **params) == {"generation": 2}
            assert calls == 2

    asyncio.run(scenario())


def test_catalog_pages_are_not_added_to_general_response_cache():
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"response": {"generation": calls}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            params = {"libCode": "00123", "type": "ALL", "pageNo": 1, "pageSize": 100}
            assert await api.request("itemSrch", **params) == {"generation": 1}
            assert await api.request("itemSrch", **params) == {"generation": 2}
            assert calls == 2

    asyncio.run(scenario())


def test_cache_key_preserves_endpoint_and_library_code_and_parameter_values():
    async def scenario():
        calls = []

        def handler(request):
            calls.append((request.url.path, request.url.params.get("libCode")))
            return httpx.Response(200, json={"response": {"generation": len(calls)}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            first = await api.request("bookExist", isbn13=ISBN, libCode="00123")
            # 입력 순서만 바뀐 동일 요청은 같은 캐시 항목입니다.
            assert await api.request("bookExist", libCode="00123", isbn13=ISBN) == first
            second = await api.request("bookExist", isbn13=ISBN, libCode="123")
            third = await api.request("srchDtlList", isbn13=ISBN)
            assert first != second != third
            assert [code for _, code in calls[:2]] == ["00123", "123"]
            assert len(calls) == 3

    asyncio.run(scenario())


def test_concurrent_identical_requests_share_one_in_flight_call():
    async def scenario():
        calls = 0
        started, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return httpx.Response(200, json={"response": {"result": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            first = asyncio.create_task(api.request("srchDtlList", isbn13=ISBN))
            await started.wait()
            second = asyncio.create_task(api.request("srchDtlList", isbn13=ISBN))
            await asyncio.sleep(0)
            release.set()
            assert await asyncio.gather(first, second) == [{"result": "ok"}] * 2
            assert calls == 1

    asyncio.run(scenario())


def test_cancelled_waiter_does_not_cancel_another_waiters_shared_call():
    async def scenario():
        calls = 0
        started, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return httpx.Response(200, json={"response": {"result": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            first = asyncio.create_task(api.request("srchDtlList", isbn13=ISBN))
            await started.wait()
            second = asyncio.create_task(api.request("srchDtlList", isbn13=ISBN))
            await asyncio.sleep(0)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            release.set()
            assert await asyncio.wait_for(second, timeout=1) == {"result": "ok"}
            assert calls == 1

    asyncio.run(scenario())


def test_daily_quota_is_safe_503_and_cools_down_uncached_calls_globally():
    async def scenario():
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("bookExist"):
                return httpx.Response(200, json={"response": {
                    "error": "1일 500건 이용 한도를 초과했습니다. 서버 IP 등록이 필요합니다. authKey=test-secret"
                }})
            return httpx.Response(200, json={"response": {"result": "ok"}})

        clock = Clock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client, clock)
            saved = await api.request("srchDtlList", isbn13=ISBN)
            with pytest.raises(HTTPException) as caught:
                await api.request("bookExist", isbn13=ISBN, libCode="00123")
            error = caught.value
            assert error.status_code == 503
            assert error.headers["Retry-After"] == "60"
            assert "500" in str(error.detail) and "IP" in str(error.detail)
            assert "test-secret" not in str(error.detail)
            # 이미 성공한 응답은 사용하고, 다른 endpoint의 새 외부 호출은 막습니다.
            assert await api.request("srchDtlList", isbn13=ISBN) == saved
            with pytest.raises(HTTPException) as paused:
                await api.request("libSrch", region="25")
            assert paused.value.status_code == 503
            assert len(calls) == 2
            clock.now = 60
            assert await api.request("libSrch", region="25") == {"result": "ok"}
            assert len(calls) == 3

    asyncio.run(scenario())


def test_http_429_is_not_retried_and_returns_retry_after():
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(429)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            with pytest.raises(HTTPException) as caught:
                await api.request("libSrch", region="25")
            assert caught.value.status_code == 503
            assert caught.value.headers["Retry-After"] == "60"
            assert calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transient_http_server_failure_is_retried_once(status):
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(status)
            return httpx.Response(200, json={"response": {"result": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            assert await api.request("srchDtlList", isbn13=ISBN) == {"result": "ok"}
            assert calls == 2

    asyncio.run(scenario())


def test_exhausted_http_retries_are_bounded_and_failure_is_not_cached():
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            for _ in range(2):
                with pytest.raises(HTTPException) as caught:
                    await api.request("srchDtlList", isbn13=ISBN)
                assert caught.value.status_code == 502
                assert "test-secret" not in str(caught.value.detail)
            assert calls == 4

    asyncio.run(scenario())


def test_authentication_error_is_not_retried_or_cached_or_echoed():
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(200, json={"response": {
                    "error": "인증키가 유효하지 않습니다. https://data4library.kr/api/libSrch?authKey=test-secret"
                }})
            return httpx.Response(200, json={"response": {"result": "ok"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            with pytest.raises(HTTPException) as caught:
                await api.request("libSrch", region="25")
            assert caught.value.status_code == 502 and calls == 1
            assert "test-secret" not in str(caught.value.detail)
            assert "authKey=" not in str(caught.value.detail)
            assert await api.request("libSrch", region="25") == {"result": "ok"}
            assert calls == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [[], {}, {"response": []}])
def test_malformed_response_is_not_cached_or_returned_as_empty_result(payload):
    async def scenario():
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            body = payload if calls == 1 else {"response": {"result": "ok"}}
            return httpx.Response(200, json=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            with pytest.raises(HTTPException) as caught:
                await api.request("srchDtlList", isbn13=ISBN)
            assert caught.value.status_code == 502
            assert await api.request("srchDtlList", isbn13=ISBN) == {"result": "ok"}
            assert calls == 2

    asyncio.run(scenario())


def test_transport_timeout_keeps_504_and_no_sensitive_url_in_detail():
    async def scenario():
        def handler(request):
            raise httpx.ReadTimeout(f"request failed: {request.url}", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = make_api(client)
            with pytest.raises(HTTPException) as caught:
                await api.request("srchDtlList", isbn13=ISBN)
            assert caught.value.status_code == 504
            assert "test-secret" not in str(caught.value.detail)
            assert "authKey=" not in str(caught.value.detail)

    asyncio.run(scenario())
