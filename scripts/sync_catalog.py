"""대전 장서를 수동으로 수집합니다. --status/--dry-run은 외부 API를 호출하지 않습니다."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from fastapi import HTTPException
import httpx

from app.clients.data4library import Data4LibraryClient
from app.core.config import Settings
from app.schemas.libraries import DISTRICT_CODES
from app.services.catalog import CatalogStore
from app.services.catalog_sync import sync_catalog


def output(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


def arguments():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=None,help="기본값은 서버의 catalog_path 설정입니다.")
    parser.add_argument("--district",choices=list(DISTRICT_CODES),help="생략하면 대전 전체. manifest는 항상 대전 전체를 검증합니다.")
    parser.add_argument("--page-size",type=int,default=100,help="외부 API 페이지 크기. 기본값 100; 제공기관의 지원 범위를 따르세요.")
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--resume",action="store_true",help="기본 동작: 완료한 도서관을 건너뛰고 미완료 수집을 재개합니다.")
    group.add_argument("--refresh",action="store_true",help="완료한 도서관도 전체 장서를 다시 검증한 뒤 교체합니다.")
    offline=parser.add_mutually_exclusive_group()
    offline.add_argument("--status",action="store_true",help="저장된 수집 범위와 완료/실패 상태만 확인합니다(외부 호출 없음).")
    offline.add_argument("--dry-run",action="store_true",help="저장된 manifest 기준 작업 계획만 확인합니다(외부 호출 없음).")
    parser.add_argument("--max-libraries",type=int,help="이번 실행에서 수집할 도서관 수를 제한합니다. 부분 범위는 완료로 표시하지 않습니다.")
    return parser.parse_args()


async def run(args):
    settings=Settings.from_env()
    path=args.db or getattr(settings,"catalog_path",ROOT/"work/data/catalog.sqlite3")
    store=CatalogStore(path)
    try:
        if args.status:
            output(store.status());return 0
        if args.dry_run:
            status=store.status()
            plan=store.pending_libraries(args.district,args.refresh)
            if args.max_libraries:
                plan=plan[:args.max_libraries]
            output({"mode":"dry_run","external_requests":0,"manifest_available":status["manifest_updated_at"] is not None,
                "note":"실행 시 대전 전체 manifest를 다시 조회하므로 목록이 변경될 수 있습니다.","planned_libraries":plan})
            return 0
        if not settings.api_key:
            output({"error":"정보나루 인증키를 로컬 환경설정에 먼저 등록하세요."});return 1
        async with httpx.AsyncClient(timeout=20) as client:
            api=Data4LibraryClient(client,settings.api_key)
            status=await sync_catalog(api,store,district=args.district,refresh=args.refresh,
                page_size=args.page_size,max_libraries=args.max_libraries,on_progress=output)
        output({"event":"sync_finished","scope":args.district or "대전 전체",
            "scope_ready":store.is_ready(args.district),"status":status})
        return 0
    except HTTPException as error:
        detail=error.detail if isinstance(error.detail,str) else "도서관 API가 동기화를 완료하지 못했습니다."
        if "authkey" in detail.lower() or "http://" in detail.lower() or "https://" in detail.lower():
            detail="도서관 API가 동기화를 완료하지 못했습니다. 인증키나 원본 요청 주소는 출력하지 않습니다."
        output({"error":detail,"status_code":error.status_code,"stopped":True,"previous_snapshot_preserved":True})
        return 1
    except (ValueError,OSError):
        output({"error":"동기화 설정 또는 로컬 저장소를 확인하세요.","stopped":True,"previous_snapshot_preserved":True})
        return 1
    finally:
        store.close()


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(run(arguments())))
