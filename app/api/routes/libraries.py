"""도서관 담당 브랜치에서 여기에 경로를 추가하면 main.py 수정 없이 연결됩니다."""

from fastapi import APIRouter

router = APIRouter(prefix="/libraries", tags=["libraries"])
