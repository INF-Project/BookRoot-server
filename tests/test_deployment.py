from fastapi.testclient import TestClient

from app.core.config import Settings
from app.deployment import create_web_app


def test_web_and_api_expose_only_public_files(tmp_path):
    app = create_web_app(Settings(catalog_path=tmp_path / 'empty.sqlite3'))
    with TestClient(app) as client:
        assert client.get('/health').json() == {'status': 'ok'}
        assert 'BookRoot' in client.get('/').text
        assert client.get('/app.js').status_code == 200
        assert client.get('/api/libraries?latitude=36').status_code == 422
        for path in ('/.env', '/data/catalog.sqlite3', '/app/main.py', '/server.py', '/mock-data.js'):
            assert client.get(path).status_code == 404
