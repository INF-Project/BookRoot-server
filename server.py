"""Railway의 PORT 설정을 사용해 웹과 API를 실행합니다."""
import os

import uvicorn

from app.deployment import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), access_log=False)
