"""공통 라우터. 기능 개발 시 각 routes 파일에서 경로를 추가합니다."""
from fastapi import APIRouter
from app.api.routes import books, loans, libraries

api_router = APIRouter(prefix="/api")
api_router.include_router(books.router)
api_router.include_router(loans.router)
api_router.include_router(libraries.router)
