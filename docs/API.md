# BookRoot API 연결 규격

`feature/books-loans` 구현 기준입니다. 폴더·담당 규칙은 [COLLABORATION.md](COLLABORATION.md)를 따릅니다.

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
    "library_count": 2
  }],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

- 지역별 소장 여부 확인과 ISBN 중복 제거 후 페이지를 나눕니다. `total`은 필터 후 고유 도서 수입니다.
- `library_count`는 선택 지역의 소장 도서관 수이며 대출 가능 권수와 다릅니다.
- `authors`는 문자열 배열 또는 null입니다. 원본 문자열은 세미콜론으로 나누며 이름의 쉼표는 유지합니다.
- 미제공 데이터는 null입니다. 출판일을 판본·쇄 발행일로 단정하지 않습니다.
- 일반 검색의 출판일이 없으면 null입니다. 상세 API에 출판일이 있으면 상세 응답에 담습니다.
- 표지는 `book_image_url`을 이미지 주소로 사용하고 null/로딩 실패 시 기본 책 아이콘을 표시합니다.

### 초기 지역 검색 제한

정보나루 `srchBooks`에는 구별 검색 조건이 없어 후보마다 `libSrchByBook`으로 소장 수를 확인합니다.
DB 없이 정확한 total을 만들기 위해 **일반 검색 후보 최대 300건**을 대상으로 합니다.
300건을 넘으면 일부 결과를 전체처럼 반환하지 않고 422로 구체적인 제목·저자·ISBN 검색을 안내합니다.
요청 전체 제한시간은 30초, 외부 동시 호출은 최대 5개입니다. 결과·외부 응답은 5분 메모리 캐시합니다.
넓은 검색어까지 빠르게 지원하려면 팀 합의로 지역별 장서 인덱스 등 저장 구조를 검토해야 합니다.

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
  "loan_available": false,
  "due_date": null,
  "remaining_days": null
}
```

library_code는 숫자로 변환하지 않으며 앞의 0을 유지합니다.
상태가 미제공·미확인이면 null입니다. 조회 실패는 오류로 반환합니다.
정보나루 bookExist는 공식 매뉴얼상 전날 기준 상태이고 반납 예정일 필드가 없습니다.
현재 due_date와 remaining_days는 항상 null입니다. 대출 불가를 무조건 ‘대출 중’으로 표시하지 않습니다.

## 오류

FastAPI 기본 형식 `{"detail": "안내 문구"}`를 사용합니다.
입력 검증의 detail은 기본 오류 목록일 수도 있어 프론트는 문자열/목록을 모두 처리해야 합니다.

| HTTP | 의미 |
|---|---|
| 422 | 입력 오류, 지원하지 않는 조건, 너무 넓은 검색어 |
| 404 | 도서 상세 정보 없음 |
| 502 | 외부 API 연결·인증·응답 실패, 잘못된 응답 형식 |
| 504 | 외부 API 또는 전체 지역 검색 제한시간 초과 |
| 503 | 서버 인증키 미설정 |

인증키나 키를 포함한 원본 요청 URL을 응답·로그에 추가하지 않습니다.

## 다른 담당의 연결 지점

`GET /api/libraries`, `GET /api/libraries/by-book/{isbn13}`은 아직 구현하지 않았습니다.
도서관 담당이 app/api/routes/libraries.py와 해당 서비스를 구현하면 중앙 라우터에 연결됩니다.
검색에 필요한 소장 건수 조회만 공동 클라이언트에 있고 목록·좌표·지도·거리는 이 브랜치에서 구현하지 않습니다.

## 실제 API 검증과 표지 이용

실제 인증키가 없는 상태에서 공식 형식의 모의 응답으로 검사했습니다.
.env에 키를 설정한 후 실제 ISBN으로 검색·지역 소장 수·상세·대출을 원본과 대조해야 합니다.
표지 URL은 http/https일 수 있습니다. HTTPS 화면에서 차단되면 대체 이미지를 표시하세요.
표지 파일은 다운로드·저장·재배포하거나 AI 입력으로 사용하지 않습니다.
정보나루 표지는 비영리 서비스의 화면 표시 용도로 제공됩니다.

- [정보나루 API 안내](https://data4library.kr/apiUtilization)
- [공식 매뉴얼](https://data4library.kr/downloadApiManual) — v20260620 기준
