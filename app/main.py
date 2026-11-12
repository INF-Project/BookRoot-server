"""BookRoot 백엔드 시작점. 화면은 프런트엔드에서 제공합니다."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import APP_NAME, CORS_ORIGINS
from app.api.router import api_router

app = FastAPI(title=APP_NAME)
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                       allow_methods=["GET"], allow_headers=["Accept", "Content-Type"])
app.include_router(api_router)

@app.get("/health")
def health():
    return {"status": "ok"}
