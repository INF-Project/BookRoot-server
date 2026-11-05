from fastapi import APIRouter

from app.api.routes import books, libraries, loans

api_router = APIRouter(prefix="/api")
api_router.include_router(books.router)
api_router.include_router(loans.router)
api_router.include_router(libraries.router)
