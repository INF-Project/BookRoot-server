"""공동 HTTP 클라이언트. 원본 오류나 인증키가 포함된 URL을 노출하지 않습니다."""
import json
import socket
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from app.core import config

class LibraryAPIError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code

def request_json(endpoint: str, params: dict, timeout: float = 15) -> dict:
    if endpoint not in {"libSrch", "libSrchByBook", "srchBooks", "srchDtlList", "bookExist"}:
        raise ValueError("지원하지 않는 정보나루 API입니다.")
    if not config.DATA4LIBRARY_KEY:
        raise LibraryAPIError("정보나루 인증키가 없습니다. .env의 DATA4LIBRARY_KEY를 설정해 주세요.", 503)
    query = urlencode({**params, "authKey": config.DATA4LIBRARY_KEY, "format": "json"})
    try:
        with urlopen("https://data4library.kr/api/" + endpoint + "?" + query, timeout=timeout) as response:
            payload = response.read(5_000_001)
        if len(payload) > 5_000_000:
            raise LibraryAPIError("정보나루 응답 크기를 초과했습니다.")
        data = json.loads(payload)
        body = data["response"]
        if not isinstance(body, dict) or "error" in body or "error" in data:
            raise LibraryAPIError("정보나루에서 요청을 거절했습니다. 인증키와 요청 조건을 확인해 주세요.")
        return body
    except HTTPError:
        raise LibraryAPIError("정보나루 서버 오류가 발생했습니다.") from None
    except (TimeoutError, socket.timeout):
        raise LibraryAPIError("정보나루 응답 시간이 초과되었습니다.", 504) from None
    except URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise LibraryAPIError("정보나루 응답 시간이 초과되었습니다.", 504) from None
        raise LibraryAPIError("정보나루에 연결하지 못했습니다.") from None
    except (ValueError, KeyError, TypeError):
        raise LibraryAPIError("정보나루 응답 형식이 올바르지 않습니다.") from None
