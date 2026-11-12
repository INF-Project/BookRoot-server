"""대전 전체 도서관 manifest와 완성된 장서 snapshot으로 검색하는 로컬 카탈로그."""
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import threading
import unicodedata

from fastapi import HTTPException

from app.schemas.books import Book, BookList, SearchBook
from app.schemas.libraries import DISTRICT_CODES


def normalized_text(value):
    """제목의 띄어쓰기, 전각 문자, 영문 대소문자 차이를 흡수합니다."""
    return "".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _text(value):
    return str(value).strip() or None if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _number(value, limit):
    try:
        number = float(value)
        return number if math.isfinite(number) and abs(number) <= limit else None
    except (ValueError, TypeError):
        return None


def catalog_book(row):
    """itemSrch 서지를 변환합니다. 표지 파일과 표지 URL은 저장하지 않습니다."""
    if not isinstance(row, Mapping):
        return None
    if "doc" in row:
        row = row["doc"]
        if not isinstance(row, Mapping):
            return None
    isbn = _text(row.get("isbn13"))
    if not isbn or len(isbn) != 13 or not isbn.isascii() or not isbn.isdigit():
        return None
    authors = row.get("authors")
    if isinstance(authors, str):
        authors = [part.strip() for part in authors.split(";") if part.strip()] or None
    elif isinstance(authors, list):
        authors = [part.strip() for part in authors if isinstance(part, str) and part.strip()] or None
    else:
        authors = None
    title = _text(row.get("bookname")) or _text(row.get("title")) or "제목 정보 없음"
    publisher = _text(row.get("publisher"))
    return {
        "isbn13": isbn, "title": title, "authors": authors, "publisher": publisher,
        "publication_year": _text(row.get("publication_year")),
        "publication_date": _text(row.get("publication_date")),
    }


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _distance_km(latitude, longitude, target_latitude, target_longitude):
    if target_latitude is None or target_longitude is None:
        return None
    lat1, lat2 = math.radians(latitude), math.radians(target_latitude)
    dlat = lat2 - lat1
    dlon = math.radians(target_longitude - longitude)
    arc = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, arc))))


class CatalogStore:
    """지역 확인과 ISBN 중복 제거를 마친 카탈로그에서 정확한 total을 반환합니다."""

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            location = Path(path).expanduser().resolve()
            location.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(location)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=10000")
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS catalog_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS catalog_libraries(
                library_code TEXT PRIMARY KEY,name TEXT NOT NULL,district TEXT NOT NULL,
                address TEXT,latitude REAL,longitude REAL,telephone TEXT,homepage TEXT,
                operating_time TEXT,closed TEXT,active INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS catalog_district ON catalog_libraries(district,active);
            CREATE TABLE IF NOT EXISTS catalog_snapshots(
                library_code TEXT PRIMARY KEY REFERENCES catalog_libraries(library_code),
                completed_at TEXT,source_count INTEGER,indexed_count INTEGER,skipped_count INTEGER,duplicate_count INTEGER,
                last_attempt_at TEXT,last_attempt_status TEXT);
            CREATE TABLE IF NOT EXISTS catalog_books(
                isbn13 TEXT PRIMARY KEY,title TEXT NOT NULL,authors_json TEXT,publisher TEXT,
                publication_year TEXT,publication_date TEXT,
                search_title TEXT NOT NULL,search_authors TEXT NOT NULL,search_publisher TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS catalog_holdings(
                library_code TEXT NOT NULL REFERENCES catalog_libraries(library_code),
                isbn13 TEXT NOT NULL REFERENCES catalog_books(isbn13),
                PRIMARY KEY(library_code,isbn13));
            CREATE INDEX IF NOT EXISTS catalog_holdings_isbn ON catalog_holdings(isbn13);
        """)
        for table, columns in {
            "catalog_libraries":{"telephone":"TEXT","homepage":"TEXT","operating_time":"TEXT","closed":"TEXT"},
            "catalog_snapshots":{"skipped_count":"INTEGER","duplicate_count":"INTEGER"},
        }.items():
            existing={row[1] for row in self._db.execute(f"PRAGMA table_info({table})")}
            for name, type_name in columns.items():
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {type_name}")
        self._db.commit()

    @contextmanager
    def _connection(self):
        with self._lock:
            with self._db:
                yield self._db

    def close(self):
        with self._lock:
            self._db.close()

    def replace_manifest(self, libraries):
        """완전히 검증한 대전 전체 목록만 전달합니다. 수집 완료 여부는 별도로 보존합니다."""
        values = []
        seen = set()
        for row in libraries:
            code = _text(row.get("library_code"))
            name = _text(row.get("name"))
            district = row.get("district")
            if not code or not code.isascii() or not code.isdigit() or not name or district not in DISTRICT_CODES:
                raise ValueError("도서관 코드·이름·대전 자치구를 모두 확인한 manifest가 필요합니다.")
            if code in seen:
                raise ValueError("manifest의 도서관 코드가 중복되었습니다.")
            seen.add(code)
            lat, lon = _number(row.get("latitude"),90), _number(row.get("longitude"),180)
            if lat is None or lon is None or (lat == 0 and lon == 0):
                lat = lon = None
            values.append((code,name,district,_text(row.get("address")),lat,lon,
                _text(row.get("telephone")),_text(row.get("homepage")),_text(row.get("operating_time")),_text(row.get("closed"))))
        if not values:
            raise ValueError("비어 있는 대전 전체 manifest를 완료 처리할 수 없습니다.")
        with self._connection() as db:
            db.execute("UPDATE catalog_libraries SET active=0")
            db.executemany("""
                INSERT INTO catalog_libraries(library_code,name,district,address,latitude,longitude,telephone,homepage,operating_time,closed,active)
                VALUES(?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(library_code) DO UPDATE SET
                name=excluded.name,district=excluded.district,address=excluded.address,
                latitude=excluded.latitude,longitude=excluded.longitude,telephone=excluded.telephone,
                homepage=excluded.homepage,operating_time=excluded.operating_time,closed=excluded.closed,active=1
            """,values)
            db.execute("INSERT OR REPLACE INTO catalog_meta VALUES('manifest_updated_at',?)",(_now(),))
            db.execute("INSERT OR REPLACE INTO catalog_meta VALUES('manifest_complete','1')")

    def replace_library(self, library_code, rows: Iterable, source_count=None):
        """전체 페이지 검증 후 호출합니다. 잘못된 입력·쓰기 실패 시 기존 snapshot을 보존합니다."""
        books = {}
        raw_count,valid_count = 0,0
        for row in rows:
            raw_count += 1
            if (book := catalog_book(row)) is not None:
                valid_count += 1
                books.setdefault(book["isbn13"],book)
        if source_count is None:
            source_count = raw_count
        if isinstance(source_count,bool) or not isinstance(source_count,int) or source_count != raw_count:
            raise ValueError("전 페이지의 원본 장서 수를 모두 확인한 후 교체해야 합니다.")
        now = _now()
        with self._connection() as db:
            exists = db.execute("SELECT 1 FROM catalog_libraries WHERE library_code=? AND active=1",(library_code,)).fetchone()
            if not exists:
                raise ValueError("완전한 manifest에 없는 도서관은 수집 완료 처리할 수 없습니다.")
            db.execute("DELETE FROM catalog_holdings WHERE library_code=?",(library_code,))
            for book in books.values():
                authors_json = json.dumps(book["authors"],ensure_ascii=False) if book["authors"] else None
                db.execute("""
                    INSERT INTO catalog_books(isbn13,title,authors_json,publisher,publication_year,publication_date,
                        search_title,search_authors,search_publisher) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(isbn13) DO UPDATE SET title=excluded.title,
                        authors_json=COALESCE(excluded.authors_json,catalog_books.authors_json),
                        publisher=COALESCE(excluded.publisher,catalog_books.publisher),
                        publication_year=COALESCE(excluded.publication_year,catalog_books.publication_year),
                        publication_date=COALESCE(excluded.publication_date,catalog_books.publication_date),
                        search_title=excluded.search_title,
                        search_authors=CASE WHEN excluded.authors_json IS NULL THEN catalog_books.search_authors ELSE excluded.search_authors END,
                        search_publisher=CASE WHEN excluded.publisher IS NULL THEN catalog_books.search_publisher ELSE excluded.search_publisher END
                """,(book["isbn13"],book["title"],authors_json,book["publisher"],book["publication_year"],book["publication_date"],
                    normalized_text(book["title"]),normalized_text(" ".join(book["authors"] or [])),normalized_text(book["publisher"])))
                db.execute("INSERT INTO catalog_holdings VALUES(?,?)",(library_code,book["isbn13"]))
            db.execute("""INSERT INTO catalog_snapshots(library_code,completed_at,source_count,indexed_count,skipped_count,duplicate_count,last_attempt_at,last_attempt_status)
                VALUES(?,?,?,?,?,?,?,'complete') ON CONFLICT(library_code) DO UPDATE SET
                completed_at=excluded.completed_at,source_count=excluded.source_count,indexed_count=excluded.indexed_count,
                skipped_count=excluded.skipped_count,duplicate_count=excluded.duplicate_count,
                last_attempt_at=excluded.last_attempt_at,last_attempt_status='complete'
            """,(library_code,now,source_count,len(books),raw_count-valid_count,valid_count-len(books),now))
            db.execute("DELETE FROM catalog_books WHERE isbn13 NOT IN (SELECT isbn13 FROM catalog_holdings)")

    def mark_failure(self, library_code):
        """실패 사유의 원본 URL/키를 저장하지 않으며 이전 완료 시각과 장서를 유지합니다."""
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM catalog_libraries WHERE library_code=?",(library_code,)).fetchone():
                return
            db.execute("""INSERT INTO catalog_snapshots(library_code,last_attempt_at,last_attempt_status)
                VALUES(?,?,'failed') ON CONFLICT(library_code) DO UPDATE SET
                last_attempt_at=excluded.last_attempt_at,last_attempt_status='failed'""",(library_code,_now()))

    def _is_ready(self, db, district):
        if district is not None and district not in DISTRICT_CODES:
            raise ValueError("대전의 자치구를 선택하세요.")
        complete = db.execute("SELECT value FROM catalog_meta WHERE key='manifest_complete'").fetchone()
        if not complete or complete[0] != "1":
            return False
        condition = " AND l.district=?" if district else ""
        params = (district,) if district else ()
        row = db.execute("""SELECT COUNT(*) AS expected,COUNT(s.completed_at) AS completed
            FROM catalog_libraries l LEFT JOIN catalog_snapshots s USING(library_code)
            WHERE l.active=1"""+condition,params).fetchone()
        return row["expected"] == row["completed"]

    def is_ready(self, district=None):
        with self._connection() as db:
            return self._is_ready(db,district)

    def pending_libraries(self, district=None, refresh=False):
        if district is not None and district not in DISTRICT_CODES:
            raise ValueError("대전의 자치구를 선택하세요.")
        where,params = ["l.active=1"],[]
        if district:
            where.append("l.district=?");params.append(district)
        if not refresh:
            where.append("s.completed_at IS NULL")
        with self._connection() as db:
            return [dict(row) for row in db.execute("""SELECT l.*,s.completed_at,s.last_attempt_status
                FROM catalog_libraries l LEFT JOIN catalog_snapshots s USING(library_code) WHERE """
                +" AND ".join(where)+" ORDER BY l.district,l.name,l.library_code",params)]

    def status(self):
        with self._connection() as db:
            db.execute("BEGIN")
            manifest = db.execute("SELECT value FROM catalog_meta WHERE key='manifest_updated_at'").fetchone()
            libraries = [dict(row) for row in db.execute("""SELECT l.library_code,l.name,l.district,
                s.completed_at,s.source_count,s.indexed_count,s.skipped_count,s.duplicate_count,s.last_attempt_at,s.last_attempt_status
                FROM catalog_libraries l LEFT JOIN catalog_snapshots s USING(library_code)
                WHERE l.active=1 ORDER BY l.district,l.name,l.library_code""")]
            districts = {}
            for district in DISTRICT_CODES:
                scoped = [row for row in libraries if row["district"] == district]
                districts[district] = {"ready":self._is_ready(db,district),"expected":len(scoped),
                    "complete":sum(row["completed_at"] is not None for row in scoped)}
            count = db.execute("""SELECT COUNT(DISTINCT h.isbn13) FROM catalog_holdings h
                JOIN catalog_libraries l USING(library_code) WHERE l.active=1""").fetchone()[0]
            return {"manifest_updated_at":manifest[0] if manifest else None,"ready":self._is_ready(db,None),
                "libraries_expected":len(libraries),"libraries_complete":sum(row["completed_at"] is not None for row in libraries),
                "unique_books":count,"districts":districts,"libraries":libraries}

    def get_book(self,isbn13):
        with self._connection() as db:
            row=db.execute("""SELECT b.* FROM catalog_books b WHERE b.isbn13=? AND EXISTS(
                SELECT 1 FROM catalog_holdings h JOIN catalog_libraries l USING(library_code)
                JOIN catalog_snapshots s USING(library_code) WHERE h.isbn13=b.isbn13 AND l.active=1 AND s.completed_at IS NOT NULL)
                """,(isbn13,)).fetchone()
            if row is None:
                return None
            return Book(isbn13=row["isbn13"],title=row["title"],authors=json.loads(row["authors_json"]) if row["authors_json"] else None,
                publisher=row["publisher"],publication_year=row["publication_year"],publication_date=row["publication_date"],book_image_url=None)

    def libraries(self,district=None,isbn13=None):
        with self._connection() as db:
            db.execute("BEGIN")
            if not self._is_ready(db,district):
                raise HTTPException(503,"선택한 지역의 도서 목록을 준비 중입니다. 장서 동기화가 완료된 후 다시 검색해 주세요.")
            where,params=["l.active=1"],[]
            if district:
                where.append("l.district=?");params.append(district)
            if isbn13 is not None:
                where.append("EXISTS(SELECT 1 FROM catalog_holdings h WHERE h.library_code=l.library_code AND h.isbn13=?)")
                params.append(isbn13)
            return [dict(row) for row in db.execute("""SELECT l.library_code,l.name,l.district,l.address,l.latitude,l.longitude,
                l.telephone,l.homepage,l.operating_time,l.closed FROM catalog_libraries l WHERE """+" AND ".join(where)+" ORDER BY l.name,l.library_code",params)]

    def search(self, query, field="title", district=None, page=1, page_size=20, *, sort="relevance", latitude=None, longitude=None):
        fields = {"title":["search_title"],"author":["search_authors"],"publisher":["search_publisher"],
            "keyword":["search_title","search_authors","search_publisher","isbn13"],"isbn13":["isbn13"]}
        if field not in fields or isinstance(page,bool) or isinstance(page_size,bool) or not isinstance(page,int) or not isinstance(page_size,int) or not 1 <= page <= 1000 or not 1 <= page_size <= 100:
            raise HTTPException(422,"검색 항목과 페이지 조건을 확인하세요.")
        if sort not in {"relevance", "distance"}:
            raise HTTPException(422,"검색 정렬 조건을 확인하세요.")
        if (latitude is None) != (longitude is None):
            raise HTTPException(422,"위도와 경도는 함께 입력해 주세요.")
        if latitude is not None:
            for coordinate, limit in ((latitude,90),(longitude,180)):
                if isinstance(coordinate,bool) or not isinstance(coordinate,(int,float)) or not math.isfinite(coordinate) or abs(coordinate)>limit:
                    raise HTTPException(422,"유효한 위도와 경도를 입력해 주세요.")
        elif sort == "distance":
            raise HTTPException(422,"가까운 순으로 검색하려면 내 위치를 먼저 확인해 주세요.")
        query = normalized_text(query)
        if not query:
            raise HTTPException(422,"검색어를 입력하세요.")
        if field == "isbn13" and (len(query) != 13 or not query.isascii() or not query.isdigit()):
            raise HTTPException(422,"ISBN에는 숫자 13자리를 입력하세요.")
        where,scope_params = ["l.active=1"],[]
        if district:
            where.append("l.district=?");scope_params.append(district)
        if field == "isbn13":
            book_filter="isbn13=?";book_params=[query]
        else:
            book_filter="("+" OR ".join(f"{column} LIKE ? ESCAPE '\\'" for column in fields[field])+")"
            book_params=["%"+_like(query)+"%"]*len(fields[field])
        # 같은 ISBN의 서지를 도서관 수만큼 다시 검사하지 않도록 책 후보를 먼저 확정합니다.
        # SQLite 3.35+의 MATERIALIZED CTE는 지역 소장 JOIN 전에 이 결과를 재사용합니다.
        prefix="WITH matched AS MATERIALIZED(SELECT * FROM catalog_books WHERE "+book_filter+") "
        params=book_params+scope_params
        scoped="EXISTS(SELECT 1 FROM catalog_holdings h JOIN catalog_libraries l USING(library_code) WHERE h.isbn13=b.isbn13 AND "+" AND ".join(where)+")"
        sql=" FROM matched b WHERE "+scoped
        with self._connection() as db:
            db.execute("BEGIN")
            if not self._is_ready(db,district):
                raise HTTPException(503,"선택한 지역의 도서 목록을 준비 중입니다. 장서 동기화가 완료된 후 다시 검색해 주세요.")
            # 두 조회 사이에 다른 프로세스가 교체해도 같은 snapshot에서 total과 items를 읽습니다.
            total = db.execute(prefix+"SELECT COUNT(*)"+sql,params).fetchone()[0]
            distance_params = []
            nearest = "NULL"
            ranked_prefix = prefix.rstrip()
            if latitude is not None:
                libraries = db.execute("SELECT l.library_code,l.latitude,l.longitude FROM catalog_libraries l WHERE "+" AND ".join(where),scope_params).fetchall()
                # 도서관별 거리는 한 번만 계산하고 각 ISBN의 선택 지역 내 최소 거리를 사용합니다.
                for library in libraries:
                    distance_params.extend((library["library_code"],_distance_km(latitude,longitude,library["latitude"],library["longitude"])))
                if libraries:
                    # ISBN 인덱스로 해당 책의 소장관만 읽습니다. 27개관 전체를 매번 조회하지 않습니다.
                    nearest = "(SELECT MIN(CASE h.library_code "+" ".join("WHEN ? THEN ?" for _ in libraries)+" END) FROM catalog_holdings h WHERE h.isbn13=b.isbn13)"
            order = ("b.nearest_distance_km IS NULL,b.nearest_distance_km," if sort=="distance" else "")+"b.match_rank,b.title,b.isbn13"
            # 전체 후보의 거리를 확정하고 정렬한 후 페이지를 나눕니다.
            paged=ranked_prefix+", ranked AS MATERIALIZED(SELECT b.*,"+nearest+""" AS nearest_distance_km,
                CASE WHEN b.search_title=? THEN 0 WHEN b.search_title LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END AS match_rank
            """+sql+"), selected AS MATERIALIZED(SELECT b.* FROM ranked b ORDER BY "+order+""" LIMIT ? OFFSET ?)
            SELECT b.*,(SELECT COUNT(*) FROM catalog_holdings h JOIN catalog_libraries l USING(library_code)
                WHERE h.isbn13=b.isbn13 AND """+" AND ".join(where)+") AS library_count FROM selected b ORDER BY "+order
            rows=db.execute(paged,[*book_params,*distance_params,query,_like(query)+"%",*scope_params,page_size,(page-1)*page_size,*scope_params]).fetchall()
            items = [SearchBook(isbn13=row["isbn13"],title=row["title"],
                authors=json.loads(row["authors_json"]) if row["authors_json"] else None,
                publisher=row["publisher"],publication_year=row["publication_year"],
                publication_date=row["publication_date"],book_image_url=None,library_count=row["library_count"],nearest_distance_km=row["nearest_distance_km"]) for row in rows]
            return BookList(items=items,total=total,page=page,page_size=page_size)
