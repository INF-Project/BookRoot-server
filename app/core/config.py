import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_name: str = "BookRoot API"
    api_key: str = ""
    source_page_size: int = 50
    max_search_candidates: int = 300
    search_timeout_seconds: float = 30
    search_backend: str = "catalog"
    catalog_path: Path = Path(__file__).resolve().parents[2] / "work/data/catalog.sqlite3"

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        backend = os.getenv("BOOK_SEARCH_BACKEND", "").strip() or "catalog"
        if backend not in {"catalog", "remote"}:
            raise ValueError("BOOK_SEARCH_BACKEND에는 catalog 또는 remote를 사용하세요.")
        db_path = os.getenv("CATALOG_DB_PATH", "").strip()
        path = Path(db_path) if db_path else cls.catalog_path
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return cls(
            app_name=os.getenv("APP_NAME", "BookRoot API"),
            api_key=os.getenv("DATA4LIBRARY_API_KEY", "").strip(),
            search_backend=backend, catalog_path=path,
        )
