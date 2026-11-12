# 도서관 백엔드 연동 안내

## 역할

프런트: 사용자 위치 권한 요청, 책 검색 화면, 결과 표시, 도서관 클릭 시 카카오 지도 표시.
친구 백엔드: 키워드 검색·책 상세·대출 상태.
내 백엔드: ISBN별 소장 도서관, 대전 자치구 필터, 사용자 좌표 기준 직선거리 정렬.

서버에서 화면·지도 SDK·카카오 키를 제공하지 않습니다. 카카오 JavaScript 키는 프런트에서 설정하고 프런트가 열리는 도메인을 카카오에 등록하세요. 기존 .env의 KAKAO_JS_KEY는 이 서버에서 읽지 않습니다.

## 실행·설정

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API 문서: http://127.0.0.1:8000/docs
서버 상태: http://127.0.0.1:8000/health
루트 / 는 화면을 제공하지 않으므로 404가 정상입니다.

.env: DATA4LIBRARY_KEY에 인증키 설정. 프런트가 다른 출처에서 실행되면 CORS_ORIGINS에 실제 프런트 주소를 쉼표로 구분하여 추가 후 재시작하세요. 예: CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
포트는 프런트 실제 실행 포트로 바꾸세요. 인증키는 프런트로 보내지 않습니다.

## 소장 도서관 거리순 조회

GET /api/libraries/by-book/{isbn13}?latitude=36.35&longitude=127.38&district=유성구

- isbn13: 숫자 13자리 문자열. 친구 검색 결과에서 전달
- latitude, longitude: 프런트가 브라우저 위치 기능으로 얻어 함께 전달
- district: 동구 / 중구 / 서구 / 유성구 / 대덕구. 생략하면 대전 전체
- 프런트의 district=all은 이 서버에 전달하지 말고 district를 생략
- 좌표가 있으면 해당 도서 소장 도서관 전체를 모아 직선거리 오름차순 정렬
- 좌표 없으면 이름순. 좌표 없는 도서관은 거리 null, 목록 뒤에 배치
- 결과 클릭 시 해당 항목 latitude / longitude로 지도 이동

응답 예시(형식 설명용 가상 값):

```json
{"items":[{"library_code":"001234","name":"예시 도서관","address":"대전광역시 유성구 ...","district":"유성구","latitude":36.35,"longitude":127.38,"distance_km":0.0,"phone":""}],"total":1}
```

전체 도서관 조회는 GET /api/libraries이며 같은 쿼리를 받습니다.
정보나루 libSrch / libSrchByBook, 대전 지역코드 25를 사용합니다. 거리 단위는 km이며 길찾기 거리가 아닙니다. 도서관 코드는 문자열로 보존하세요.

422 잘못된 입력 / 503 인증키 미설정 / 502 외부 응답 오류 / 504 시간 초과.
오류 형식은 {"detail":"안내 문구"}. 실제 조회 실패를 빈 목록이나 예시 데이터로 바꾸지 않습니다.

## 첨부 BookRoot-source.zip과의 차이

첨부 소스는 프런트이며 api.js가 /districts, /search를 호출합니다. 이 경로들은 현재 백엔드에 없습니다. API_BASE_URL만 바꾸면 연동되는 상태가 아닙니다.

프런트와 친구가 연결할 흐름: 친구의 /api/books/search → 선택한 책 isbn13 → 내 /api/libraries/by-book/{isbn13} → 각 library_code로 친구의 대출 상태 API.

프런트 id는 library_code, distanceKm은 distance_km, districtId는 district로 변환해야 합니다. 구 ID 매핑: yuseong=유성구, seo=서구, jung=중구, dong=동구, daedeok=대덕구. 지도에는 위도·경도를 사용합니다. 제목·저자·출판사·출판일은 친구의 책 API 응답에서 가져옵니다.

통합 /api/search 및 /api/districts를 채택하려면 팀 공통 응답을 먼저 합의하고 별도 통합 작업이 필요합니다. 첨부 예시의 대출부수·대기인원·서가위치는 현재 정보나루 응답만으로 보장하지 않습니다. 임의 값을 생성하지 않습니다.

## 검증

.\.venv\Scripts\python.exe -m unittest discover -s tests -v
외부 API는 대체 응답으로 검증합니다. 실제 키 연동 및 프런트 브라우저 확인은 별도 필요합니다.
