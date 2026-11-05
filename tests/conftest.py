from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def book(number, **fields):
    return {"isbn13": f"978{number:010d}", "bookname": f"연습 도서 {number}",
            "authors": "저자 A; 저자 B", "publisher": "가상 출판사", "publication_year": "2026",
            "bookImageURL": "https://example.com/cover.jpg", **fields}


class FakeAPI:
    def __init__(self, rows, holdings):
        self.rows, self.holdings = rows, holdings
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        params = request.url.params
        assert params["authKey"] == "test-secret" and params["format"] == "json"
        if request.url.path.endswith("srchBooks"):
            start = (int(params["pageNo"]) - 1) * int(params["pageSize"])
            return httpx.Response(200, json={"response": {"numFound": len(self.rows),
                "docs": [{"doc": row} for row in self.rows[start:start + int(params["pageSize"])]]}})
        assert request.url.path.endswith("libSrchByBook")
        assert params["region"] == "25"
        count = self.holdings.get((params["isbn"], params.get("dtl_region")), 0)
        return httpx.Response(200, json={"response": {"numFound": count}})


@contextmanager
def client_for(rows=(), holdings=None, **settings):
    fake = FakeAPI(list(rows), holdings or {})
    with TestClient(create_app(Settings(api_key="test-secret", **settings), httpx.MockTransport(fake))) as client:
        yield client, fake


def search(client, **params):
    return client.get("/api/books/search", params={"q": "파이썬", **params})
