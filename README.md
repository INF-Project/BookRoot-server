# BookRoot Server

BookRoot 팀의 Python + FastAPI 서버 저장소입니다.
대전광역시 도서관에 소장된 도서를 검색하는 API를 제공합니다.
제목·저자·출판사·ISBN 검색, 대전 5개 구 필터, 책 표지 URL, 상세, 대출 가능 상태가 포함되어 있습니다.
구를 먼저 선택하고 그 지역에 소장된 책을 검색합니다. 지도·도서관 전체 목록·거리는 친구 담당입니다.
DB 모델·마이그레이션은 아직 만들지 않았습니다.

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
실제 검색에는 `.env`의 `DATA4LIBRARY_API_KEY`가 필요합니다.
[도서관 정보나루](https://data4library.kr/apiUtilization)에서 인증키를 발급받아 입력하고 서버를 재시작하세요.
키가 없어도 /health와 /docs는 사용 가능하지만 검색은 키 설정 안내와 503을 반환합니다.
실제 API 키로 검증하지 못한 상태이며, 자동 테스트는 공식 응답 형식의 모의 데이터로 실행합니다.
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

일반 도서 검색에 구 조건을 전달하는 방식이 아니라, 도서 후보의 ISBN으로 지역별 소장 여부를 확인합니다.
대전 또는 선택 구에 소장 도서관이 한 곳 이상인 책만 반환합니다. 같은 ISBN은 검색 결과에서 중복하지 않습니다.
외부 후보 최대 300개를 지역 확인·중복 제거한 뒤 페이지를 나눕니다.
응답은 items, 필터 후 total, page, page_size입니다.
후보가 300건을 초과하면 422로 제목·저자·ISBN을 구체적으로 입력하도록 안내합니다.
지역 조회 전체 제한시간은 30초입니다. 넓은 검색어를 빠르게 지원하려면 장서 인덱스 등 저장 구조를 검토합니다.
상세 규격은 [API 문서](docs/API.md)를 보세요.

표지는 `book_image_url`을 화면의 이미지 주소로 사용합니다. 값이 없거나 로딩 실패 시 기본 책 아이콘을 표시합니다.
서버는 이미지를 내려받거나 저장하지 않습니다. 정보나루 표지는 비영리 서비스의 화면 표시 용도로 이용합니다.
출판연도는 `publication_year`이며 특정 판본·쇄의 발행일을 뜻하지 않습니다.

현재 API는 DB 없이 동작하며 외부 응답은 5분 동안 메모리에 캐시합니다.
서버 재시작 시 캐시는 사라집니다. 대출 상태는 공식 매뉴얼상 전날 기준이며 반납 예정일·잔여일은 현재 null입니다.

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
