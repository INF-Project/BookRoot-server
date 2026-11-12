"""친구 담당: 소장 여부 및 대출 가능 상태 조회."""
from fastapi import APIRouter
router = APIRouter(prefix="/books", tags=["loans"])
