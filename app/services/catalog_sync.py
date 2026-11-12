"""정보나루의 대전 전체 manifest와 도서관별 전체 장서를 수동 동기화합니다."""
from collections.abc import Mapping
from math import ceil

from fastapi import HTTPException

from app.schemas.libraries import DISTRICT_CODES
from app.services.catalog import CatalogStore, catalog_book


def _page(body,collection,wrapper,page,page_size,total=None):
    if not isinstance(body,Mapping):
        raise HTTPException(502,"장서 동기화 응답 형식을 확인할 수 없습니다.")
    count=body.get("numFound")
    if isinstance(count,bool) or not str(count).isascii() or not str(count).isdigit():
        raise HTTPException(502,"장서 동기화의 전체 건수를 확인할 수 없습니다.")
    count=int(count)
    if total is not None and count!=total:
        raise HTTPException(502,"동기화 중 원본 전체 건수가 변경되었습니다. 기존 장서는 유지됩니다.")
    rows=body.get(collection,[])
    expected=min(page_size,max(0,count-(page-1)*page_size))
    if not isinstance(rows,list) or len(rows)!=expected or any(
        not isinstance(row,Mapping) or not isinstance(row.get(wrapper),Mapping) for row in rows):
        raise HTTPException(502,"동기화할 원본 페이지를 모두 받지 못했습니다. 기존 장서는 유지됩니다.")
    return [row[wrapper] for row in rows],count


async def _libraries(api,params,page_size):
    body=await api.request("libSrch",**params,pageNo=1,pageSize=page_size)
    rows,total=_page(body,"libs","lib",1,page_size)
    for page in range(2,ceil(total/page_size)+1):
        body=await api.request("libSrch",**params,pageNo=page,pageSize=page_size)
        more,_=_page(body,"libs","lib",page,page_size,total)
        rows.extend(more)
    codes=[str(row.get("libCode") or "") for row in rows]
    if any(not code or not code.isascii() or not code.isdigit() for code in codes) or len(set(codes))!=total:
        raise HTTPException(502,"대전 도서관 코드 목록을 모두 확인하지 못했습니다.")
    return rows


async def collect_manifest(api,page_size=100):
    """선택 구만 조회한 목록을 대전 전체 manifest로 오인하지 않도록 전 범위를 대조합니다."""
    all_rows=await _libraries(api,{"region":"25"},page_size)
    if not all_rows:
        raise HTTPException(502,"대전 전체 도서관 목록이 비어 있어 동기화를 시작하지 않았습니다.")
    codes={str(row["libCode"]) for row in all_rows}
    districts={}
    for district,code in DISTRICT_CODES.items():
        rows=await _libraries(api,{"region":"25","dtl_region":code},page_size)
        for row in rows:
            library_code=str(row["libCode"])
            if library_code not in codes or library_code in districts:
                raise HTTPException(502,"대전 전체 목록과 자치구 목록이 일치하지 않습니다. 다시 동기화하세요.")
            districts[library_code]=district
    if set(districts)!=codes:
        raise HTTPException(502,"일부 대전 도서관의 자치구를 확인하지 못했습니다. 완료 처리하지 않습니다.")
    return [{"library_code":str(row["libCode"]),"name":row.get("libName"),
        "district":districts[str(row["libCode"])],"address":row.get("address"),
        "latitude":row.get("latitude"),"longitude":row.get("longitude"),
        "telephone":row.get("tel"),"homepage":row.get("homepage"),
        "operating_time":row.get("operatingTime"),"closed":row.get("closed")} for row in all_rows]


async def collect_library_books(api,library_code,page_size=100):
    params={"libCode":library_code,"type":"ALL","pageSize":page_size}
    body=await api.request("itemSrch",**params,pageNo=1)
    first,total=_page(body,"docs","doc",1,page_size)
    # 부가적인 원본 필드와 표지 URL을 메모리/DB에 보관하지 않습니다.
    rows=[catalog_book(row) or {} for row in first]
    for page in range(2,ceil(total/page_size)+1):
        body=await api.request("itemSrch",**params,pageNo=page)
        more,_=_page(body,"docs","doc",page,page_size,total)
        rows.extend(catalog_book(row) or {} for row in more)
    return rows,total


async def sync_catalog(api,store:CatalogStore,district=None,refresh=False,page_size=100,max_libraries=None,on_progress=None):
    """실패 시 즉시 중단합니다. 재개 시 완료한 도서관을 건너뛰며 부분 수집 구는 ready가 아닙니다."""
    if district is not None and district not in DISTRICT_CODES:
        raise ValueError("대전의 자치구를 선택하세요.")
    if isinstance(page_size,bool) or not isinstance(page_size,int) or not 1<=page_size<=1000:
        raise ValueError("페이지 크기는 1~1000 사이 정수로 지정하세요.")
    if max_libraries is not None and (isinstance(max_libraries,bool) or not isinstance(max_libraries,int) or max_libraries<1):
        raise ValueError("수집할 도서관 수는 1 이상이어야 합니다.")
    progress=on_progress or (lambda event:None)
    manifest=await collect_manifest(api,page_size)
    store.replace_manifest(manifest)
    pending=store.pending_libraries(district,refresh)
    if max_libraries is not None:
        pending=pending[:max_libraries]
    progress({"event":"manifest_complete","libraries":len(manifest),"to_sync":len(pending)})
    for library in pending:
        code=library["library_code"]
        progress({"event":"library_start","library_code":code,"name":library["name"]})
        try:
            rows,total=await collect_library_books(api,code,page_size)
            store.replace_library(code,rows,source_count=total)
        except BaseException:
            store.mark_failure(code)
            raise
        progress({"event":"library_complete","library_code":code,"source_count":total})
    return store.status()
