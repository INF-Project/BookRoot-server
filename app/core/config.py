"""환경설정 로딩. 인증키는 실제 값 대신 .env에 저장합니다."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
APP_NAME = os.getenv("APP_NAME", "BookRoot API")
DATA4LIBRARY_KEY = os.getenv("DATA4LIBRARY_KEY", "")

# 프런트엔드 개발 서버 주소를 쉼표로 구분해 설정합니다.
CORS_ORIGINS = [value.strip() for value in os.getenv("CORS_ORIGINS", "").split(",") if value.strip()]
