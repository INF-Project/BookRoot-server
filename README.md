# BookRoot Server

BookRoot 팀의 Python + FastAPI 서버 저장소입니다.
현재는 개발 환경과 서버 실행 확인만 구성했습니다. 도서 검색·지도·대출 기능과 데이터베이스는 아직 추가하지 않았습니다.

## 개발 환경

- Python 3.14
- FastAPI
- Git / GitHub
- VS Code + Microsoft Python 확장

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
가상환경의 Python을 직접 실행하므로 PowerShell 실행 정책 변경이나 별도 활성화는 필요하지 않습니다.

- 서버 확인: <http://localhost:8000/health> → `{"status":"ok"}`
- API 문서: <http://localhost:8000/docs>
- 종료: 터미널에서 `Ctrl+C`

다음에 서버를 켤 때는 마지막 uvicorn 명령만 실행합니다.
포트가 이미 사용 중이면 기존 서버를 종료하거나 `--port 8001`로 바꿉니다.

VS Code의 `Ctrl+Shift+P → Python: Select Interpreter`에서
이 프로젝트의 `.venv\Scripts\python.exe`를 선택합니다.

## 파일 역할

```text
app/
  __init__.py
  main.py              # 서버 시작점과 상태 확인 API
.env.example           # 팀에 공유하는 환경설정 예시
.gitignore             # Git에 올리지 않을 파일
.python-version        # 팀에서 사용하는 Python 버전
requirements.txt       # 설치할 라이브러리
```

`.venv`와 `.env`는 각자 만들며 GitHub에 올리지 않습니다.
환경설정을 추가할 때에는 실제 값 대신 예시를 `.env.example`에 기록합니다.

## 다음 기능 작업 시작하기

작업 중인 변경이 없는 상태에서 main의 최신 코드를 가져오고 기능 브랜치를 만듭니다.

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/book-search
```

기능을 수정한 다음 확인하고 커밋합니다.

```powershell
git diff
git add app
git commit -m "feat: add book search"
git push -u origin feature/book-search
```

수정한 README나 requirements.txt가 있다면 해당 파일도 `git add`에 포함합니다.
GitHub에서 Pull Request를 열어 팀원 확인 후 main에 합칩니다.
