# BookRoot API 연결 규격

`feature/deploy-preview` 구현 기준입니다. 폴더·담당 규칙은 [COLLABORATION.md](COLLABORATION.md)를 따릅니다.

## 지역 선택 후 도서 검색

```http
GET /api/books/search?q=정확한책제목&district=유성구&page=1&page_size=20
```

화면 순서는 **구 선택 → 책 검색**입니다. 구를 선택하면 그 구 도서관의 소장 도서만 반환합니다.
`district` 생략은 ‘대전 전체’를 선택한 경우이며, 다른 도시의 소장 도서는 반환하지 않습니다.

| Query | 규칙 |
|---|---|
| `q` | 필수. 공백 제거 후 1~100자 |
| `district` | 동구 / 중구 / 서구 / 유성구 / 대덕구. 생략 시 대전 전체 |
| `field` | 기본 title. title / author / publisher / keyword / isbn13 |
| `page` | 기본 1. 1~1000 |
| `page_size` | 기본 20. 1~100 |
| `sort` | relevance(기본) / distance. distance는 좌표가 필요하며 catalog 모드에서 지원 |
| `latitude`, `longitude` | 두 값을 함께 전달. 위도 -90~90, 경도 -180~180의 유한값 |

ISBN 검색은 숫자 문자열 13자리입니다. cursor 방식은 사용하지 않습니다.

가상 응답 예:

```json
{
  "items": [{
    "isbn13": "9780000000002",
    "title": "연습용 파이썬 도서",
    "authors": ["예제 저자"],
    "publisher": "가상 출판사",
    "publication_year": "2026",
    "publication_date": null,
    "book_image_url": "https://example.com/cover.jpg",
    "library_count": 2,
    "nearest_distance_km": null
  }],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

- 지역별 소장 여부 확인과 ISBN 중복 제거 후 페이지를 나눕니다. `total`은 필터 후 고유 도서 수입니다.
- `library_count`는 선택 지역의 소장 도서관 수이며 대출 가능 권수와 다릅니다.
- `nearest_distance_km`는 선택 지역 내 가장 가까운 소장 도서관까지의 직선거리입니다. 사용자 위치나 소장관 좌표가 없으면 null입니다.
- `sort=distance`는 지역 확인·중복 제거 후 전체 책 후보의 최소 거리를 계산하고 정렬한 다음 페이지를 나눕니다. 좌표 없는 책은 마지막이며, 같은 거리에서는 제목 일치도·제목·ISBN 순입니다.
- 좌표를 전달하고 `sort=relevance`를 유지하면 기존 제목 정렬과 함께 최근접 거리를 제공합니다. 좌표만 한 값 또는 좌표 없는 distance 요청은 422입니다.
- `authors`는 문자열 배열 또는 null입니다. 원본 문자열은 세미콜론으로 나누며 이름의 쉼표는 유지합니다.
- 미제공 데이터는 null입니다. 출판일을 판본·쇄 발행일로 단정하지 않습니다.
- 일반 검색의 출판일이 없으면 null입니다. 상세 API에 출판일이 있으면 상세 응답에 담습니다.
- 표지는 `book_image_url`을 이미지 주소로 사용하고 null/로딩 실패 시 기본 책 아이콘을 표시합니다.

### 지역 장서 DB 검색

2026-11-12 사용자 승인으로 기본 검색을 SQLite 지역 장서 DB로 변경했습니다.
`BOOK_SEARCH_BACKEND`의 기본값은 `catalog`이며 전국 후보 300건 제한을 적용하지 않습니다.
`libSrch`의 대전 도서관 목록과 도서관별 `itemSrch(type=ALL)` 전체 장서를 수동 동기화합니다.
검색은 외부 호출 없이 저장된 ISBN·소장 관계로 지역 필터, 중복 제거, 정확한 total, 페이지를 계산합니다.
제목·저자·출판사는 공백과 영문 대소문자를 정규화하며 제목 완전 일치 결과를 먼저 표시합니다.
장서 DB는 수집 시점의 목록이며 실시간 대출 상태가 아닙니다. 표지 URL이 없으면 null입니다.

선택 지역의 도서관 중 한 곳이라도 초기 수집이 미완료이면 503을 반환합니다.
수집 실패·부분 수집을 검색 결과 0건으로 바꾸지 않습니다. 갱신 중 실패하면 기존 완성 목록을 보존합니다.
`scripts/sync_catalog.py`의 상태 조회와 동기화 사용법은 README를 참조하세요.

명시적으로 `BOOK_SEARCH_BACKEND=remote`를 설정하면 이전 전국 후보 확인 방식으로 동작합니다.
이 호환 모드는 기존 300건/30초 제한을 유지하며 일반 서비스의 기본 검색으로 사용하지 않습니다.

## 책 상세

```http
GET /api/books/{isbn13}
```

책 기본 필드와 book_image_url을 바로 반환합니다 (items로 감싸지 않음).
출판일을 제공받으면 publication_date에 담습니다. 도서가 없으면 404입니다.

## 대출 가능 여부

```http
GET /api/books/{isbn13}/availability?library_code=00123
```

```json
{
  "isbn13": "9780000000002",
  "library_code": "00123",
  "has_book": true,
  "loan_available": false
}
```

library_code는 숫자로 변환하지 않으며 앞의 0을 유지합니다.
상태가 미제공·미확인이면 null입니다. 조회 실패는 오류로 반환합니다.
정보나루 bookExist는 공식 매뉴얼상 전날 기준 상태이고 반납 예정일 필드가 없습니다.
반납 예정일·잔여 대출 기간·예약은 현재 정보나루 연동으로 제공하지 않으며 응답에도 포함하지 않습니다.
2026-11-12 재검토에서도 대전공공도서관의 공개된 별도 API 규격을 확인하지 못했습니다.
웹 화면에 표시되는 기능을 외부 이용이 보장된 API로 간주하지 않습니다. 별도 정식 연동 경로가 확보되면 재검토합니다.
예정일은 ISBN 단위 한 날짜가 아니라 실제 소장본·등록번호별 데이터가 필요하며, 임의 날짜로 잔여일을 만들지 않습니다.
대출 불가를 무조건 ‘대출 중’으로 표시하지 않습니다.

## 오류

FastAPI 기본 형식 `{"detail": "안내 문구"}`를 사용합니다.
입력 검증의 detail은 기본 오류 목록일 수도 있어 프론트는 문자열/목록을 모두 처리해야 합니다.

| HTTP | 의미 |
|---|---|
| 422 | 입력 오류, 지원하지 않는 조건, 너무 넓은 검색어 |
| 404 | 도서 상세 정보 없음 |
| 502 | 외부 API 연결·인증·응답 실패, 잘못된 응답 형식 |
| 504 | 외부 API 또는 전체 지역 검색 제한시간 초과 |
| 503 | 서버 인증키 미설정, 장서 DB 초기 수집 미완료, 정보나루 요청 한도·IP 등록 제한 |

인증키나 키를 포함한 원본 요청 URL을 응답·로그에 추가하지 않습니다.

정보나루가 `1일 500건 이상 요청 시 IP 등록 필요`를 반환하면 원인을 명시한 503과 Retry-After를 반환합니다.
한도 제한은 인증키 오류로 표시하거나 자동 반복 재시도하지 않습니다. 짧은 전역 대기 동안 새 원본 호출을 중지합니다.
동일 외부 요청은 병합하며 성공한 서지·도서관 응답은 캐시하고, 대출 응답은 60초만 캐시합니다.
일시적인 5xx·연결 오류만 한 번 재시도하며 실패를 정상 응답 캐시에 저장하지 않습니다.

## 다른 담당의 연결 지점

`GET /api/libraries`, `GET /api/libraries/by-book/{isbn13}`은 아직 구현하지 않았습니다.
도서관 담당이 app/api/routes/libraries.py와 해당 서비스를 구현하면 중앙 라우터에 연결됩니다.
책 목록의 최근접 거리 정렬은 catalog 검색에서 구현합니다. 도서관 목록·좌표·지도는 로컬 연결용 코드로 시연 중이며 정식 도서관 담당 API 통합은 별도로 필요합니다.

## 실제 API 검증과 표지 이용

자동 테스트는 공식 형식의 모의 응답으로 검사합니다.
2026-11-12 로컬 인증키로 실제 ISBN의 유성구 검색·상세·대출 조회가 정상 응답하는 것을 확인했습니다.
표지 URL은 http/https일 수 있습니다. HTTPS 화면에서 차단되면 대체 이미지를 표시하세요.
표지 파일은 다운로드·저장·재배포하거나 AI 입력으로 사용하지 않습니다.
정보나루 표지는 비영리 서비스의 화면 표시 용도로 제공됩니다.

- [정보나루 API 안내](https://data4library.kr/apiUtilization)
- [공식 매뉴얼](https://data4library.kr/downloadApiManual) — v20260620 기준
- [정보나루 bookExist 기준 시점 안내](https://data4library.kr/noticeV?cn=129)

## 도서관 목록

GET /api/libraries 및 GET /api/libraries/by-book/{isbn13}는 items/total을 반환합니다. district와 쌍으로 입력하는 latitude/longitude를 지원하며, 좌표가 있으면 직선거리순, 없으면 이름순입니다. 거리 미확인 결과는 마지막입니다. telephone, homepage, operating_time, closed는 제공 시에만 표시합니다. 기본 catalog 모드는 검색과 같은 장서 snapshot을 사용하므로 외부 API 한도와 무관하게 소장관을 조회합니다.
