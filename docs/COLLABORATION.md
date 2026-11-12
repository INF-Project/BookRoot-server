# BookRoot 협업 구조 제안

도서관·소장 조회·구 필터·직선거리 정렬을 구현했습니다. 검색·대출 API는 친구 담당으로 아직 구현 전입니다. 이 문서는 팀 합의용 제안이며 기존 팀 규칙이 있으면 조정하세요.

## 폴더와 담당

```text
app/
  main.py                      서버 실행·health (공동)
  core/config.py               환경설정 (공동)
  api/
    router.py                  라우터 연결 (공동)
    routes/
      books.py                 친구: 검색·상세 요청
      loans.py                 친구: 대출 상태 요청
      libraries.py             나: 도서관·소장 목록·구 필터·거리순
  schemas/
    books.py                   친구: 책 응답 모델
    loans.py                   친구: 대출 응답 모델
    libraries.py               나: 도서관 응답 모델
  services/
    books.py                   친구: 검색·상세 처리
    loans.py                   친구: 대출 상태 처리
    libraries.py               나: 소장 도서관·필터 처리
    distance.py                나: 직선거리 계산
  clients/data4library.py       공동: 정보나루 호출
tests/                         담당별 테스트
  test_books.py                친구
  test_loans.py                친구
  test_libraries.py            나
  test_distance.py             나
docs/COLLABORATION.md           팀 연결 규칙
```

routes는 입력과 HTTP 응답, services는 기능 처리, clients는 외부 API 통신, schemas는 반환 필드를 담당합니다. 아직 DB가 필요하다고 확정되지 않아 models나 migrations는 만들지 않습니다. 테스트 파일은 기능 구현 시 추가합니다.

## 연결 규칙

- 책 ID: `isbn13` 문자열 (숫자형 변환 금지)
- 도서관 ID: `library_code` 문자열 (앞의 0 보존)
- 위도·경도: `latitude`, `longitude` (WGS84)
- 거리: `distance_km` 숫자 또는 null, 직선거리 km. 좌표 없는 결과는 뒤로 배치
- 구: `district` = 동구 / 중구 / 서구 / 유성구 / 대덕구. 생략하면 대전 전체
- 출판연도 `publication_year`와 출판일 `publication_date`를 분리. 판본일로 단정하지 않음
- 응답의 미제공 값은 null. 대출 상태 조회 실패를 false로 바꾸지 않음

## API 경로 (검색·대출은 제안, 도서관 경로는 구현됨)

| 담당 | 요청 | 역할 |
|---|---|---|
| 친구 | GET /api/books/search?q=파이썬&page=1&page_size=20 | 검색 |
| 친구 | GET /api/books/{isbn13} | 상세 |
| 친구 | GET /api/books/{isbn13}/availability?library_code=... | 대출 가능 상태 |
| 나 | GET /api/libraries?district=유성구&latitude=36.35&longitude=127.38 | 전체 도서관, 필터·거리순 |
| 나 | GET /api/libraries/by-book/{isbn13}?district=유성구&latitude=36.35&longitude=127.38 | 해당 책 소장 도서관 |

검색 경로 `/search`는 `/{isbn13}`보다 먼저 등록하세요. 좌표는 두 값을 함께 입력하고, 없으면 이름순입니다. 위도 -90~90, 경도 -180~180의 유한값만 허용합니다.

목록 응답은 `{"items": [...], "total": 0}`로 통일합니다. 검색에는 `page`, `page_size`도 포함합니다. 거리 정렬은 조회한 대전 소장 도서관 전체에 적용한 후 페이지를 나눠야 합니다. 책 목록 자체의 거리순 정렬은 별도 합의가 필요한 기능입니다.

책 기본 필드: isbn13, title, authors, publisher, publication_year, publication_date. authors는 문자열 배열로 통일하고 API 원본 변환은 친구가 담당합니다.
도서관 기본 필드: library_code, name, address, district, latitude, longitude, distance_km.
대출 응답: isbn13, library_code, has_book, loan_available, due_date, remaining_days. 상태 미확인은 null을 허용합니다. due_date와 remaining_days는 데이터 제공 확인 전 null로 둡니다.

잘못된 입력은 422, 외부 API 실패는 502, 제한시간 초과는 504로 구분합니다. 오류 본문은 FastAPI 기본 `{"detail": "안내 문구"}`를 사용합니다. 키가 포함된 외부 요청 URL을 로그나 응답에 노출하지 않습니다.

## 화면 연결

책 검색 → isbn13 선택 → 소장 도서관 조회 → library_code 선택 → 대출 상태 조회.
프런트 담당자가 소장 도서관 응답 좌표로 지도를 표시합니다. 사용자 위치는 브라우저 위치 기능으로 구하고 서버에서 직선거리를 계산합니다. 구별 필터 자체에는 지도 API가 필요하지 않습니다. 지도 SDK는 별도 프런트엔드에서 사용하며 화면 구현 시 공개용 JavaScript 키와 등록 도메인을 설정합니다.

## 공동 파일 충돌 줄이기

친구 브랜치: feature/books-loans / 내 브랜치: feature/libraries-map.
팀의 기준 브랜치가 develop인지 확인하고 그 브랜치에서 각각 작업합니다. main.py는 이미 라우터가 연결되어 있어 기능 추가 때 수정할 필요가 없습니다. 공동 파일과 requirements.txt 변경은 먼저 알리고 작은 PR로 합칩니다. .env와 인증키는 커밋하지 않습니다.

도서관 기능 실행·설정·제약은 docs/LIBRARIES.md를 참고하세요. 인증키 발급 후 실제 응답 검증이 필요합니다.
