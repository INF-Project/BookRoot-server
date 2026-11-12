import asyncio
import sqlite3

from fastapi import HTTPException
import pytest

from app.schemas.libraries import DISTRICT_CODES
from app.services.catalog import CatalogStore, catalog_book
from app.services.catalog_sync import sync_catalog


def manifest():
    rows=[{"library_code":f"00{i:03}","name":f"{gu} 도서관","district":gu,
        "address":f"대전광역시 {gu} 테스트로","latitude":"36.35","longitude":"127.38",
        "telephone":"042-000-0000","homepage":"https://example.org/","operating_time":"09:00~18:00","closed":"월요일"}
        for i,gu in enumerate(DISTRICT_CODES,1)]
    rows.append({**next(row for row in rows if row["district"]=="유성구"),"library_code":"00999","name":"유성구 두번째"})
    return rows


def book(number,title="카탈로그 테스트",authors="저자 A;저자 B",publisher="테스트 출판사"):
    return {"isbn13":str(9780000000000+number),"bookname":title,"authors":authors,"publisher":publisher,
        "publication_year":2021,"bookImageURL":"https://example.org/must-not-be-saved.jpg"}


@pytest.fixture
def store(tmp_path):
    result=CatalogStore(tmp_path/"catalog.sqlite3")
    yield result
    result.close()


def complete(store):
    store.replace_manifest(manifest())
    for lib in manifest():
        store.replace_library(lib["library_code"],[])


def code(gu):
    return next(row["library_code"] for row in manifest() if row["district"]==gu)


def test_no_catalog_or_partial_district_never_ready(store):
    assert not store.is_ready(None)
    store.replace_manifest(manifest())
    store.replace_library(code("유성구"),[book(1)])
    assert not store.is_ready("유성구") and not store.is_ready(None)
    with pytest.raises(HTTPException) as error:
        store.search("테스트",district="유성구")
    assert error.value.status_code==503
    assert "sqlite" not in error.value.detail.lower()
    store.replace_library("00999",[])
    assert store.is_ready("유성구") and not store.is_ready(None)
    assert store.search("테스트",district="유성구").total==1


def test_exact_filtered_total_dedup_and_page_after_region(store):
    complete(store)
    store.replace_library(code("유성구"),[book(1),book(2),book(1)])
    store.replace_library("00999",[book(1)])
    store.replace_library(code("서구"),[book(3),book(1)])
    first=store.search("테스트",district="유성구",page=1,page_size=1)
    second=store.search("테스트",district="유성구",page=2,page_size=1)
    assert first.total==second.total==2
    assert first.items[0].isbn13!=second.items[0].isbn13
    assert first.items[0].library_count==2
    all_books=store.search("테스트",page_size=100)
    assert all_books.total==3
    assert next(item for item in all_books.items if item.isbn13==book(1)["isbn13"]).library_count==3
    assert store.search("테스트",district="동구").total==0


def test_more_than_300_local_books_are_searchable(store):
    complete(store)
    store.replace_library(code("유성구"),[book(i) for i in range(450)])
    result=store.search("테스트",district="유성구",page=4,page_size=100)
    assert result.total==450 and len(result.items)==100
    assert len({item.isbn13 for item in result.items})==100


def test_whitespace_casefold_literal_wildcards_and_authors(store):
    complete(store)
    store.replace_library(code("유성구"),[
        book(1,"불편한 편의점 ＡＢＣ",authors=[" Kim ","저자 B"],publisher="Publisher NAME"),
        book(2,"100%_A",authors=None),book(3,"100xxA",authors=None)])
    assert store.search("불편한편의점 abc",district="유성구").total==1
    assert store.search("KIM",field="author",district="유성구").total==1
    assert store.search("publishername",field="publisher",district="유성구").total==1
    assert store.search("저자b",field="keyword",district="유성구").total==1
    assert store.search("%_",district="유성구").items[0].isbn13==book(2)["isbn13"]
    assert store.search("%_",district="유성구").total==1
    detail=store.get_book(book(1)["isbn13"])
    assert detail.authors==["Kim","저자 B"] and detail.publication_year=="2021"
    assert detail.publication_date is None and detail.book_image_url is None
    assert store.get_book(book(2)["isbn13"]).authors is None


def test_isbn_search_is_exact_and_returns_original_string(store):
    complete(store)
    raw={**book(1),"isbn13":"0012345678901"}
    store.replace_library(code("유성구"),[raw])
    assert store.search("0012345678901",field="isbn13").items[0].isbn13=="0012345678901"
    with pytest.raises(HTTPException):store.search("1234",field="isbn13")


def test_atomic_replacement_rolls_back_writes_on_sql_failure(store):
    complete(store)
    library=code("유성구")
    store.replace_library(library,[book(1,"기존 데이터")])
    old=store.status()["libraries"]
    with store._connection() as db:
        db.execute("""CREATE TRIGGER test_catalog_failure BEFORE INSERT ON catalog_holdings
            WHEN NEW.isbn13='9780000000002' BEGIN SELECT RAISE(ABORT,'simulated write error'); END""")
    with pytest.raises(sqlite3.IntegrityError):store.replace_library(library,[book(2,"새 데이터")])
    assert store.status()["libraries"]==old
    assert store.search("기존 데이터").total==1
    assert store.get_book(book(2)["isbn13"]) is None


def test_incomplete_or_failing_rows_preserve_previous_snapshot(store):
    complete(store)
    library=code("유성구")
    store.replace_library(library,[book(1)])
    with pytest.raises(ValueError):store.replace_library(library,[book(2)],source_count=2)
    def broken():
        yield book(2)
        raise RuntimeError("interrupted collection")
    with pytest.raises(RuntimeError):store.replace_library(library,broken())
    store.mark_failure(library)
    assert store.is_ready("유성구") and store.search("테스트",district="유성구").total==1
    status=next(row for row in store.status()["libraries"] if row["library_code"]==library)
    assert status["last_attempt_status"]=="failed" and status["completed_at"] is not None


def test_new_manifest_library_requires_its_complete_snapshot(store):
    complete(store)
    added={**manifest()[0],"library_code":"00888","district":"유성구"}
    store.replace_manifest([*manifest(),added])
    assert not store.is_ready("유성구") and not store.is_ready(None)
    assert store.is_ready("서구")
    store.replace_library("00888",[])
    assert store.is_ready(None)


def test_retired_library_is_excluded_from_search_and_lookup(store):
    complete(store)
    store.replace_library("00999",[book(1)])
    store.replace_manifest([row for row in manifest() if row["library_code"]!="00999"])
    assert store.is_ready(None)
    assert store.search("테스트").total==0
    assert store.get_book(book(1)["isbn13"]) is None


def test_invalid_isbn_and_duplicates_recorded_without_cover_data(store):
    complete(store)
    store.replace_library(code("유성구"),[book(1),book(1),{**book(2),"isbn13":"978-invalid"}])
    row=next(row for row in store.status()["libraries"] if row["library_code"]==code("유성구"))
    assert (row["source_count"],row["indexed_count"],row["skipped_count"],row["duplicate_count"])==(3,1,1,1)
    with store._connection() as db:
        assert "book_image_url" not in {row[1] for row in db.execute("PRAGMA table_info(catalog_books)")}
    assert "bookImageURL" not in catalog_book(book(1))


def test_library_metadata_and_holdings_use_region_before_return(store):
    complete(store)
    store.replace_library(code("유성구"),[book(1)])
    store.replace_library(code("서구"),[book(2)])
    rows=store.libraries("유성구",book(1)["isbn13"])
    assert len(rows)==1 and rows[0]["library_code"]==code("유성구")
    assert rows[0]["telephone"]=="042-000-0000" and rows[0]["latitude"]==36.35
    assert store.libraries("서구",book(1)["isbn13"])==[]


def distance_catalog(store):
    rows=manifest()
    for row in rows:
        if row["library_code"]=="00999":
            row["latitude"]=36.45
        elif row["district"]=="동구":
            row["latitude"]=row["longitude"]=None
        elif row["district"]=="서구":
            row["latitude"]=36.40
    store.replace_manifest(rows)
    for row in rows:
        store.replace_library(row["library_code"],[])
    # 관련도 1등 책은 먼 곳에, 관련도 2등 책은 가까운 곳에 둡니다.
    store.replace_library("00999",[book(1,"검색"),book(2,"검색 가까운 책")])
    store.replace_library(code("유성구"),[book(2,"검색 가까운 책")])
    store.replace_library(code("서구"),[book(1,"검색")])
    store.replace_library(code("동구"),[book(3,"검색 좌표 없음")])


def test_distance_orders_entire_scoped_set_before_paging_and_deduplicates(store):
    distance_catalog(store)
    options={"latitude":36.35,"longitude":127.38,"sort":"distance","page_size":1}
    first=store.search("검색",page=1,**options)
    second=store.search("검색",page=2,**options)
    third=store.search("검색",page=3,**options)
    assert first.total==second.total==third.total==3
    assert [result.items[0].isbn13 for result in [first,second,third]]==[book(2)["isbn13"],book(1)["isbn13"],book(3)["isbn13"]]
    assert first.items[0].nearest_distance_km==0 and first.items[0].library_count==2
    assert 5<second.items[0].nearest_distance_km<6
    assert third.items[0].nearest_distance_km is None
    assert store.search("검색",page=4,**options).items==[]


def test_distance_uses_only_selected_district_and_changes_with_location(store):
    distance_catalog(store)
    result=store.search("검색",district="유성구",sort="distance",latitude=36.35,longitude=127.38)
    assert result.total==2
    assert result.items[0].isbn13==book(2)["isbn13"]
    assert 11<result.items[1].nearest_distance_km<12  # 더 가까운 서구 소장은 제외
    reverse=store.search("검색",district="유성구",sort="distance",latitude=36.45,longitude=127.38)
    assert reverse.items[0].isbn13==book(1)["isbn13"]  # 같은 거리에서는 제목 완전 일치 먼저
    assert reverse.items[0].nearest_distance_km==0


def test_relevance_remains_default_and_no_location_does_not_invent_distance(store):
    distance_catalog(store)
    normal=store.search("검색")
    assert normal.items[0].isbn13==book(1)["isbn13"]
    assert all(row.nearest_distance_km is None for row in normal.items)
    located=store.search("검색",latitude=36.35,longitude=127.38)
    assert located.items[0].isbn13==book(1)["isbn13"]
    assert located.items[0].nearest_distance_km>5


def test_equal_distances_have_stable_pages_and_retired_libraries_do_not_count(store):
    complete(store)
    store.replace_library(code("유성구"),[book(2),book(1),book(3)])
    store.replace_library("00999",[book(4)])
    store.replace_manifest([row for row in manifest() if row["library_code"]!="00999"])
    pages=[store.search("테스트",sort="distance",latitude=36.35,longitude=127.38,page_size=1,page=n) for n in range(1,4)]
    assert all(page.total==3 for page in pages)
    assert [page.items[0].isbn13 for page in pages]==[book(n)["isbn13"] for n in (1,2,3)]


@pytest.mark.parametrize("options",[
    {"sort":"distance"},{"latitude":36.35},{"longitude":127.38},
    {"latitude":float("nan"),"longitude":127.38},
    {"latitude":36.35,"longitude":float("inf")},
    {"latitude":91,"longitude":127.38},{"latitude":36.35,"longitude":181},
    {"latitude":True,"longitude":127.38},{"sort":"bad"},
])
def test_invalid_distance_conditions_are_422(store,options):
    with pytest.raises(HTTPException) as error:
        store.search("검색",**options)
    assert error.value.status_code==422


def test_catalog_distance_api_contract(tmp_path):
    import httpx
    from fastapi.testclient import TestClient
    from app.core.config import Settings
    from app.main import create_app

    path=tmp_path/"distance.sqlite3"
    catalog=CatalogStore(path)
    distance_catalog(catalog)
    catalog.close()
    def no_network(request):
        raise AssertionError("거리 검색에 외부 통신이 필요하지 않습니다.")
    with TestClient(create_app(Settings(catalog_path=path),httpx.MockTransport(no_network))) as client:
        params={"q":"검색","sort":"distance","latitude":36.35,"longitude":127.38,"district":"유성구","page_size":1}
        response=client.get("/api/books/search",params=params)
        assert response.status_code==200
        assert response.json()["total"]==2
        assert response.json()["items"][0]["nearest_distance_km"]==0
        assert response.json()["items"][0]["isbn13"]==book(2)["isbn13"]
        for invalid in [{"latitude":"nan"},{"longitude":"Infinity"},{"latitude":91},{"sort":"bad"}]:
            assert client.get("/api/books/search",params={**params,**invalid}).status_code==422


class Source:
    def __init__(self):
        self.calls=[];self.books={};self.failure=None;self.missing_district=None;self.changed_page=None
    async def request(self,endpoint,**params):
        self.calls.append((endpoint,params))
        if self.failure and self.failure(endpoint,params):raise HTTPException(429,"외부 API 이용량 제한")
        page,size=params["pageNo"],params["pageSize"]
        if endpoint=="libSrch":
            rows=manifest()
            if params.get("dtl_region"):
                gu=next(gu for gu,code in DISTRICT_CODES.items() if code==params["dtl_region"])
                rows=[] if self.missing_district==gu else [row for row in rows if row["district"]==gu]
            rows=[{"lib":{"libCode":row["library_code"],"libName":row["name"],"address":row["address"],
                "latitude":row["latitude"],"longitude":row["longitude"]}} for row in rows]
            return {"numFound":len(rows),"libs":rows[(page-1)*size:page*size]}
        assert endpoint=="itemSrch" and params["type"]=="ALL"
        rows=self.books.get(params["libCode"],[])
        count=len(rows)+(1 if self.changed_page==(params["libCode"],page) else 0)
        return {"numFound":count,"docs":[{"doc":row} for row in rows[(page-1)*size:page*size]]}


def test_sync_partial_scope_and_resume_never_mark_all_ready(store):
    api=Source();api.books[code("유성구")]=[book(1),book(2),book(3)]
    asyncio.run(sync_catalog(api,store,district="유성구",page_size=2,max_libraries=1))
    assert not store.is_ready("유성구") and not store.is_ready(None)
    calls_before=len(api.calls)
    asyncio.run(sync_catalog(api,store,district="유성구",page_size=2))
    assert store.is_ready("유성구") and not store.is_ready(None)
    assert store.search("테스트",district="유성구").total==3
    new_item_codes={params["libCode"] for endpoint,params in api.calls[calls_before:] if endpoint=="itemSrch"}
    assert len(new_item_codes)==1
    assert {params.get("dtl_region") for endpoint,params in api.calls if endpoint=="libSrch"}=={None,*DISTRICT_CODES.values()}


def test_sync_changed_page_total_stops_and_keeps_previous_complete_data(store):
    complete(store);api=Source();library=code("유성구")
    store.replace_library(library,[book(1,"이전 snapshot")])
    api.books[library]=[book(2),book(3),book(4)]
    api.changed_page=(library,2)
    # 이름순에서 유성구 기본 도서관보다 '두번째'가 먼저 나오므로 명시적으로 그 도서관도 정상 처리됩니다.
    with pytest.raises(HTTPException) as error:
        asyncio.run(sync_catalog(api,store,district="유성구",refresh=True,page_size=2))
    assert error.value.status_code==502
    assert store.search("이전 snapshot",district="유성구").total==1
    assert store.get_book(book(2)["isbn13"]) is None
    assert api.calls[-1][0]=="itemSrch" and api.calls[-1][1]["pageNo"]==2


def test_quota_failure_causes_immediate_stop_without_later_requests(store):
    api=Source();api.failure=lambda endpoint,params:True
    with pytest.raises(HTTPException):asyncio.run(sync_catalog(api,store))
    assert len(api.calls)==1 and not store.is_ready(None)
    assert store.status()["manifest_updated_at"] is None


def test_manifest_district_coverage_mismatch_never_publishes_partial_snapshot(store):
    api=Source();api.missing_district="유성구"
    with pytest.raises(HTTPException):asyncio.run(sync_catalog(api,store))
    assert store.status()["manifest_updated_at"] is None
    assert not any(endpoint=="itemSrch" for endpoint,_ in api.calls)


def test_disk_catalog_survives_new_store_instance(tmp_path):
    path=tmp_path/"persist.sqlite3"
    a=CatalogStore(path);complete(a);a.replace_library(code("유성구"),[book(1)]);a.close()
    b=CatalogStore(path)
    assert b.is_ready("유성구") and b.search("テスト" ).total==0
    assert b.search("테스트").total==1
    b.close()
