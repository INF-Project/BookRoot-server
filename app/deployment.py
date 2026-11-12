"""API와 정식 웹 화면을 같은 주소에서 제공합니다."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import create_app


def create_web_app(settings=None, transport=None):
    app = create_app(settings, transport=transport)
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "web", html=True), name="web")
    return app


app = create_web_app()
