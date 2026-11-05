"""BookRoot FastAPI 서버의 시작 파일입니다."""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.router import api_router
from app.clients.data4library import Data4LibraryClient
from app.core.config import Settings
from app.services.books import BooksService
from app.services.loans import LoansService


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            library_api = Data4LibraryClient(client, settings.api_key)
            application.state.data4library = library_api
            application.state.books = BooksService(library_api, settings)
            application.state.loans = LoansService(library_api)
            yield

    application = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

    @application.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    application.include_router(api_router)
    return application


app = create_app()
