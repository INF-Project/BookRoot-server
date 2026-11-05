import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from conftest import book


@pytest.mark.parametrize("has_book,available,expected", [
    ("Y", "Y", (True, True)), ("Y", "N", (True, False)),
    ("N", "N", (False, False)), (None, "?", (None, None)), ("N", "Y", (False, None)),
])
def test_loan_values_preserve_unknown_and_library_leading_zeros(has_book, available, expected):
    def handler(request):
        assert request.url.params["libCode"] == "00123"
        assert request.url.params["isbn13"] == book(1)["isbn13"]
        return httpx.Response(200, json={"response": {"result": {"hasBook": has_book, "loanAvailable": available}}})
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        result = client.get(f"/api/books/{book(1)['isbn13']}/availability", params={"library_code": "00123"})
        assert result.status_code == 200
        data = result.json()
        assert (data["has_book"], data["loan_available"]) == expected
        assert data["library_code"] == "00123"
        assert data["due_date"] is None and data["remaining_days"] is None


@pytest.mark.parametrize("library_code", ["", "abc", "-1", "123456789012345678901"])
def test_invalid_library_code(library_code):
    with TestClient(create_app(Settings())) as client:
        assert client.get(f"/api/books/{book(1)['isbn13']}/availability", params={"library_code": library_code}).status_code == 422


def test_unavailable_source_is_not_false_loan_status():
    handler = lambda request: httpx.Response(500)
    with TestClient(create_app(Settings(api_key="test-secret"), httpx.MockTransport(handler))) as client:
        result = client.get(f"/api/books/{book(1)['isbn13']}/availability", params={"library_code": "00123"})
        assert result.status_code == 502 and "detail" in result.json()
