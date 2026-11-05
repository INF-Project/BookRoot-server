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

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        return cls(
            app_name=os.getenv("APP_NAME", "BookRoot API"),
            api_key=os.getenv("DATA4LIBRARY_API_KEY", "").strip(),
        )
