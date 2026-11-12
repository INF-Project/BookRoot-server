# BookRoot Server

BookRoot 팀의 Python + FastAPI 서버 저장소입니다.
대전광역시 도서관에 소장된 도서를 검색하는 API를 제공합니다.
제목·저자·출판사·ISBN 검색, 대전 5개 구 필터, 책 표지 URL, 상세, 대출 가능 상태가 포함되어 있습니다.
구를 먼저 선택하고 해당 지역의 책·소장관을 검색합니다. web/에는 지도·위치·표지·대출 상태 화면이 포함됩니다. 검색은 SQLite 장서 snapshot을 사용합니다.

## 개발 환경

- Python 3.14
- FastAPI
- Git / GitHub
- IntelliJ IDEA + Python 플러그인 또는 VS Code + Microsoft Python 확장

## 처음 실행하기 (Windows PowerShell)

팀원은 저장소를 내려받습니다. 이미 이 폴더를 열었다면 clone과 cd는 생략합니다.

```powershell
git clone https://github.com/INF-Project/BookRoot-server.git
cd BookRoot-server
```

README.md와 requirements.txt가 있는 폴더에서 실행합니다.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`.env`가 이미 있다면 복사 명령은 생략합니다.
장서 DB가 준비되면 검색·소장관 조회는 키 없이 가능합니다. 표지·상세 보강과 대출 상태에는 `.env`의 `DATA4LIBRARY_API_KEY`가 필요합니다.
[도서관 정보나루](https://data4library.kr/apiUtilization)에서 인증키를 발급받아 입력하고 서버를 재시작하세요.
DB가 없는 새 환경에서는 검색에 503으로 수집 필요를 안내합니다. 자동 테스트는 외부 통신 없이 모의 데이터로 실행합니다.
가상환경의 Python을 직접 실행하므로 PowerShell 실행 정책 변경이나 별도 활성화는 필요하지 않습니다.

- 서버 확인: <http://localhost:8000/health> → `{"status":"ok"}`
- API 문서: <http://localhost:8000/docs>
- 검색 예: `/api/books/search?q=파이썬&district=유성구`
- 종료: 터미널에서 `Ctrl+C`

다음에 서버를 켤 때는 마지막 uvicorn 명령만 실행합니다.
포트가 이미 사용 중이면 기존 서버를 종료하거나 `--port 8001`로 바꿉니다.

IntelliJ의 Python SDK/Interpreter 설정에서 이 프로젝트의 `.venv\Scripts\python.exe`를 선택합니다.
VS Code에서는 `Ctrl+Shift+P → Python: Select Interpreter`로 같은 파일을 선택합니다.

## 파일 역할

```text
app/
  __init__.py
  main.py              # 서버 시작점과 공통 오류 처리
  core/config.py       # 환경설정
  api/router.py        # 중앙 라우터
  api/routes/          # books, loans, libraries
  schemas/             # 기능별 응답 모델
  services/            # 검색·상세·대출·캐시, 친구 구현 자리
  clients/data4library.py # 공동 외부 통신
docs/API.md            # 프론트엔드·다른 AI와 공유할 API 규격
docs/COLLABORATION.md  # 폴더와 담당 범위
tests/                 # 외부 네트워크 없이 실행하는 동작 검사
.env.example           # 팀에 공유하는 환경설정 예시
.gitignore             # Git에 올리지 않을 파일
.python-version        # 팀에서 사용하는 Python 버전
requirements.txt       # 설치할 라이브러리
```

`.venv`와 `.env`는 각자 만들며 GitHub에 올리지 않습니다.
환경설정을 추가할 때에는 실제 값 대신 예시를 `.env.example`에 기록합니다.

## 다음 기능 작업 시작하기

작업 중인 변경이 없는 상태에서 develop의 최신 코드를 가져오고 기능 브랜치를 만듭니다.

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c feature/your-feature
```

기능을 수정한 다음 확인하고 커밋합니다.

```powershell
git diff
git add app
git commit -m "feat: add book search"
git push -u origin feature/your-feature
```

수정한 README나 requirements.txt가 있다면 해당 파일도 `git add`에 포함합니다.
GitHub에서 develop을 대상으로 Pull Request를 열어 팀원 확인 후 합칩니다.

## 검색 동작과 표지 표시

기본 검색은 SQLite에 수집한 대전 도서관 장서에서 처리합니다. 전국 후보 300건 제한을 적용하지 않습니다.
도서관별 전체 장서를 수집한 뒤 선택 구에 소장된 ISBN을 중복 제거하여 total, page, page_size로 반환합니다.
제목·저자·출판사·키워드·ISBN 검색을 지원하며 제목 완전 일치 결과를 먼저 표시합니다.
서버의 API 호출 한도와 무관하게 준비된 장서 목록을 검색할 수 있습니다.
초기 수집이 끝나지 않은 구는 503으로 안내하며, 부분 결과를 전체 또는 0건으로 표시하지 않습니다.
상세 규격은 [API 문서](docs/API.md)를 보세요.

표지는 `book_image_url`을 화면의 이미지 주소로 사용합니다. 값이 없거나 로딩 실패 시 기본 책 아이콘을 표시합니다.
서버는 이미지를 내려받거나 저장하지 않습니다. 정보나루 표지는 비영리 서비스의 화면 표시 용도로 이용합니다.
출판연도는 `publication_year`이며 특정 판본·쇄의 발행일을 뜻하지 않습니다.

SQLite 장서 DB는 서버 재시작 후에도 유지하며 파일은 Git에 포함하지 않습니다.
외부 서지·소장 정보는 성공 응답을 캐시하고 같은 요청을 병합하며, 대출 상태 캐시는 60초입니다.
대출 상태는 공식 매뉴얼상 전날 기준이며 반납 예정일·잔여 대출 기간·예약은 현재 정보나루 연동으로 제공하지 않습니다.
대전공공도서관 웹 화면의 기능을 별도 공개 API로 간주하지 않으며, 해당 기능은 정식 연동 규격이 확보되면 재검토합니다.
책 검색은 사용자 좌표와 `sort=distance`를 전달하면 선택 지역 내 최근접 소장 도서관의 직선거리순으로 전체 결과를 정렬한 뒤 페이지를 나눕니다. 응답 필드는 `nearest_distance_km`이며, 좌표가 없는 책은 마지막에 표시합니다.

## 장서 DB 준비와 요청 한도

기본 DB 경로는 `work/data/catalog.sqlite3`이며 `CATALOG_DB_PATH`로 변경할 수 있습니다.
`BOOK_SEARCH_BACKEND` 기본값은 `catalog`입니다. `remote`는 이전 방식 검증을 위한 호환 모드입니다.
설정 이름은 `.env.example`에 있고 인증키는 기존 `.env`에서만 읽습니다.

정보나루는 등록되지 않은 호출 서버 IP에서 1일 500건 이상 요청하면 제한합니다.
초기 수집 전 정보나루 로그인 → 마이페이지에서 **API를 호출하는 서버의 공인 IP**를 등록해야 합니다.
`localhost`, `127.0.0.1`, 사설 IP를 등록하는 것이 아닙니다. 개발 PC와 배포 서버의 공인 IP는 다를 수 있습니다.
현재 제한 오류는 `인증키 오류`로 뭉개지 않고 IP 등록 필요와 한도를 안내하며 반복 호출을 중지합니다.
한도를 우회하려고 키나 IP를 교체·순환하지 않습니다.

동기화 CLI는 먼저 상태·예상 작업을 확인한 뒤 실행합니다. 실제 수집에는 API 호출이 발생합니다.
갱신 실패 시 기존의 완성된 도서관 장서 snapshot을 보존하며 중간 결과를 공개하지 않습니다.
수집 상태·마지막 갱신 시각은 CLI 상태에서 확인합니다. 상세 명령은 `scripts/sync_catalog.py --help`를 사용하세요.

- [정보나루 호출 IP 등록 정책](https://data4library.kr/noticeV?cn=88)
- [정보나루 API 안내](https://data4library.kr/apiUtilization)

추가 경로:

```text
GET /api/books/{isbn13}
GET /api/books/{isbn13}/availability?library_code=00123
```

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

GitHub Actions에서도 같은 검사를 실행합니다. API 키나 외부 네트워크는 필요하지 않습니다.

2026-11-12 로컬 초기 수집은 정보나루가 공개한 월별 CSV와 참여 도서관 위치 XLSX로 완료했습니다. 27개관, 중복 제거 740638권이며 장서 기준은 2026년 10월입니다. 공개 파일 수집은 work/import_public_catalog.py, 파일별 출처와 SHA-256은 work/data/public-files/sources.json에 있습니다. CSV·장서 DB는 Git에 넣지 않습니다. API 동기화 CLI는 이후 갱신용이며 서버 IP 등록이 필요합니다.

## 화면 실행과 Railway 배포

`python server.py`로 웹과 API를 함께 실행합니다. PORT 환경변수의 기본값은 8000입니다. API만 개발할 때는 기존 uvicorn 명령을 사용합니다.

GitHub에는 코드만 저장하며 DB와 키는 넣지 않습니다. `python scripts/prepare_release.py`는 work/deploy-preview/production에 코드·화면·일관된 SQLite 복사본을 준비합니다. 폴더가 이미 있으면 --output으로 새 work 하위 폴더를 지정하세요. 준비한 폴더를 Railway CLI의 up --path-as-root --no-gitignore로 올립니다. 배포 서비스의 비공개 DATA4LIBRARY_API_KEY 설정을 별도로 등록합니다. 배포 묶음 자체에는 키가 없습니다. Dockerfile과 railway.json은 같은 폴더에 포함됩니다.

현재 미리보기는 2026년 10월 snapshot을 이미지에 포함하며 재배포 때 복원됩니다. 새 데이터로 갱신하려면 새 snapshot으로 다시 배포해야 합니다. 상시 자동 갱신에는 영구 저장소를 추가하세요. Railway 무료 체험은 최대 30일 또는 $5까지이며 유료 요금제로 자동 변경하지 않습니다. 배포 서버의 정보나루 호출 IP·요청 한도와 체험 계정의 외부 통신 제한은 별도 확인이 필요합니다.
