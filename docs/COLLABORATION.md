# BookRoot 협업 구조

기준 브랜치는 develop입니다. 책·대출 담당은 feature/books-loans, 도서관·지도 담당은 feature/libraries-map을 사용합니다.
지도 담당의 제안에 있는 ‘나/친구’ 표현은 기능 담당명으로 바꿨습니다.

```text
app/
  main.py                     공동: 서버·health·서비스 수명 관리
  core/config.py              공동: 환경설정
  api/router.py               공동: 라우터 연결
  api/routes/
    books.py                  책·대출: 검색·상세
    loans.py                  책·대출: 대출 상태
    libraries.py              도서관·지도: 도서관·소장 목록
  schemas/
    books.py                  책·대출: 책 응답 모델
    loans.py                  책·대출: 대출 응답 모델
    libraries.py              도서관·지도: 도서관 응답·구 코드
  services/
    books.py                  책·대출: 검색·상세 처리
    loans.py                  책·대출: 상태 처리
    libraries.py              도서관·지도: 소장·구 필터 (구현 예정)
    distance.py               도서관·지도: 직선거리 (구현 예정)
    cache.py                  공용: 크기·유효기간 제한 캐시
  clients/data4library.py     공동: 정보나루 통신
web/                          도서관·지도: 향후 화면 위치
tests/
  conftest.py                 공용 모의 응답
  test_books.py               책·대출 담당
  test_loans.py               책·대출 담당
docs/API.md                   실제 API 규격·오류·제한
```

현재 web 코드는 올리지 않습니다. 임시 프론트는 로컬 work에만 두고 .git/info/exclude로 제외합니다.
도서관/거리 테스트는 기능을 구현할 때 담당자가 추가합니다. DB 모델·마이그레이션은 만들지 않습니다.

## 연결 규칙

- isbn13, library_code는 문자열이며 앞의 0을 보존합니다.
- 좌표는 WGS84 latitude, longitude입니다. distance_km는 직선거리 km 또는 null입니다.
- district는 대전 5개 구이며 생략하면 대전 전체입니다.
- 흐름: **구 선택 → 책 검색 → isbn13 선택 → 소장 도서관 → library_code 선택 → 대출 상태**.
- 검색도 선택 구 소장 책만 반환하며 중복 제거·지역 확인 후 페이지를 나눕니다.
- /api/books/search는 /{isbn13}보다 먼저 등록합니다.
- 목록은 items/total, 검색은 page/page_size를 추가합니다.
- 책 기본 필드: isbn13, title, authors, publisher, publication_year, publication_date.
- 표지 필드 book_image_url, 검색의 소장 도서관 수 library_count를 추가합니다.
- authors는 문자열 배열 또는 null이며 미제공 데이터는 null입니다.
- 대출 필드: isbn13, library_code, has_book, loan_available, due_date, remaining_days.
- 외부 상태 미확인은 null, 조회 실패는 502/504입니다. 실패를 false로 바꾸지 않습니다.
- 오류는 FastAPI 기본 detail 형식입니다.
- 좌표 기능은 두 값을 함께 받고 범위·유한값을 검증합니다. 도서관 담당이 구현합니다.
- 거리 정렬은 조회한 지역 소장 도서관 전체에 적용한 뒤 페이지를 나눕니다.

## 이번 브랜치의 공동 변경

main.py, core/config.py, api/router.py, clients/data4library.py, requirements.txt를 변경했습니다.
이 구조를 한 번 통합한 뒤 각 담당은 routes/services/schemas의 자기 기능 파일에서 작업합니다.
외부 호출은 request.app.state.data4library.request(endpoint, **params)를 재사용할 수 있습니다.
키 주입, 호출 timeout 10초, 최대 동시 5개, 안전한 오류 처리는 공동 클라이언트가 담당합니다.
테스트는 create_app(settings, transport=httpx.MockTransport(...))로 외부 응답을 주입합니다.

지역 검색은 후보 300건과 전체 30초 제한이 있으며 초과 시 구체적인 검색을 안내합니다.
DB 도입이나 제한 변경은 팀에서 합의하고 API 문서도 수정합니다.
기능별 PR은 develop을 대상으로 하고 공동 파일 변경은 작은 단위로 공유합니다.
.env, 키, 가상환경은 커밋하지 않습니다.
