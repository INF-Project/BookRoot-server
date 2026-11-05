# BookRoot 공동 개발 규칙

- Python 3.14 + FastAPI 프로젝트입니다. 기본 통합 브랜치는 `develop`입니다.
- 기능은 별도 `feature/*` 브랜치에서 개발하고 `develop`을 대상으로 비교합니다.
- 담당·폴더 규칙은 docs/COLLABORATION.md, API 규격은 docs/API.md, 모델은 app/schemas/입니다.
- 경로·검증은 app/api/routes/, 처리는 app/services/, 외부 통신은 app/clients/data4library.py에 둡니다.
- `.env`, 인증키, 가상환경을 커밋하지 않습니다. 새 설정 이름은 `.env.example`에 값 없이 기록합니다.
- 검색 결과는 대전 또는 선택한 대전 구에 소장된 책만 반환합니다. 일반 검색에 지역 필터가 있다고 가정하지 않습니다.
- `book_image_url`은 원본 URL만 반환합니다. 표지 파일을 다운로드·저장하거나 AI 입력으로 사용하지 않습니다.
- `publication_year`를 판본일로 표시하지 않습니다. 소장 수를 대출 가능 수로 표시하지 않습니다.
- 검색은 page, page_size, 필터 후 total을 사용합니다. 지역 확인과 중복 제거 후 페이지를 나눕니다.
- authors는 문자열 배열 또는 null, 오류는 FastAPI 기본 detail 형식을 사용합니다.
- 임시 프론트는 로컬 work/에만 만들고 커밋하지 않습니다. DB 모델은 팀 결정 전 만들지 않습니다.
- 외부 API 실패를 빈 결과나 대출 불가로 바꾸지 않습니다. 오류에 인증키가 포함된 원본 URL을 노출하지 않습니다.
- 검증 명령: `python -m pytest -q` (`requirements-dev.txt` 설치 필요).
