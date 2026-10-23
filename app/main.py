"""BookRoot 서버의 시작 파일. 기능 API는 이후에 추가합니다."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title=os.getenv("APP_NAME", "BookRoot API"))


@app.get("/health")
def health():
    """서버가 정상적으로 실행 중인지 확인합니다."""
    return {"status": "ok"}
