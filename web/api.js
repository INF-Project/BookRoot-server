import { API_BASE_URL } from './config.js';

const districts = { yuseong:'유성구',seo:'서구',jung:'중구',dong:'동구',daedeok:'대덕구' };
const districtIds = Object.fromEntries(Object.entries(districts).map(([id,name]) => [name,id]));
const bookCache=new Map(),statusCache=new Map();
let availabilityBlockedUntil=0,availabilityBlockError;

function cached(cache,key) {
  const entry=cache.get(key);
  if (!entry) return null;
  if (entry.expires<=Date.now()) {cache.delete(key);return null;}
  return entry;
}
function remember(cache,key,value,ttl,extra={}) {
  cache.delete(key);cache.set(key,{value,expires:Date.now()+ttl,...extra});
  const limit=cache===bookCache ? 256 : 512;
  while(cache.size>limit)cache.delete(cache.keys().next().value);
}
function retrySeconds(value) {
  if (!value) return 0;
  const numeric=Number(value);
  if (Number.isFinite(numeric)) return Math.max(0,Math.ceil(numeric));
  const date=Date.parse(value);
  return Number.isFinite(date) ? Math.max(0,Math.ceil((date-Date.now())/1000)) : 0;
}

async function request(path,params=new URLSearchParams(),signal) {
  signal?.throwIfAborted();
  const url=new URL(`${API_BASE_URL.replace(/\/+$/,'')}${path}`,document.baseURI);
  url.search=params.toString();
  const response=await fetch(url,{headers:{Accept:'application/json'},signal});
  let data;
  try { data=await response.json(); } catch(error) {
    if(signal?.aborted || error.name==='AbortError')throw error;
    throw new Error('서버 응답을 확인할 수 없습니다.');
  }
  signal?.throwIfAborted();
  if (!response.ok) {
    const error=new Error(typeof data.detail==='string' ? data.detail : '입력한 검색 조건을 확인해 주세요.');
    error.status=response.status;
    error.retryAfter=retrySeconds(response.headers?.get('Retry-After'));
    throw error;
  }
  return data;
}

// 구 이름은 고정 선택지입니다. /districts API나 가상의 도서관 수를 사용하지 않습니다.
export async function getDistricts({signal}={}) {
  signal?.throwIfAborted();
  return Object.entries(districts).map(([id,name])=>({id,name,libraryCount:null,examples:[]}));
}

function bookModel(book) {
  return {isbn13:book.isbn13,title:book.title,author:(book.authors || []).join(' · '),
    publisher:book.publisher,publicationYear:book.publication_year,publishedAt:book.publication_date,
    coverUrl:book.book_image_url,libraryCount:book.library_count,nearestDistanceKm:book.nearest_distance_km ?? null};
}
function libraryModel(row) {
  return {id:row.library_code,name:row.name,districtId:districtIds[row.district] || null,
    neighborhood:row.address,distanceKm:row.distance_km,latitude:row.latitude,longitude:row.longitude,
    status:null,phone:row.telephone || null,hours:row.operating_time || null,
    closed:row.closed || null,homepage:row.homepage || null};
}

function applyStatus(holding,value) {
  holding.statusLoading=false;
  if(value?.has_book===false) {holding.status='unknown';holding.statusError='소장 정보가 변경되었을 수 있습니다.';}
  else holding.status=knownLoanState(value);
}

function limitRequests(maximum) {
  let active=0;
  const queue=[];
  const drain=()=>{
    while(active<maximum && queue.length) {active++;queue.shift().start();}
  };
  return (task,signal)=>new Promise((resolve,reject)=>{
    if(signal?.aborted) {reject(signal.reason);return;}
    const cancel=()=>{const index=queue.indexOf(job);if(index>=0) {queue.splice(index,1);reject(signal.reason);}};
    const job={async start() {
      signal?.removeEventListener('abort',cancel);
      try {signal?.throwIfAborted();resolve(await task());}
      catch(error) {reject(error);}
      finally {active--;drain();}
    }};
    signal?.addEventListener('abort',cancel,{once:true});
    queue.push(job);drain();
  });
}

const statusSlot=limitRequests(3),librarySlot=limitRequests(3),coverSlot=limitRequests(3);

function noteAvailabilityLimit(error) {
  if(error?.status===503 && error.retryAfter>0 && error!==availabilityBlockError) {
    availabilityBlockedUntil=Math.max(availabilityBlockedUntil,Date.now()+error.retryAfter*1000);
    availabilityBlockError=error;
  }
}

async function availabilityValue(isbn13,libraryCode,signal) {
  signal?.throwIfAborted();
  const key=`${isbn13}:${libraryCode}`;
  const saved=cached(statusCache,key);
  if(saved)return saved.value;
  return statusSlot(async()=>{
    const existing=cached(statusCache,key);
    if(existing)return existing.value;
    if(availabilityBlockedUntil>Date.now())throw availabilityBlockError;
    try {
      const value=await request(`/books/${isbn13}/availability`,new URLSearchParams({library_code:libraryCode}),signal);
      remember(statusCache,key,value,60000);
      return value;
    } catch(error) {noteAvailabilityLimit(error);throw error;}
  },signal);
}

function knownLoanState(value) {
  if(value?.has_book!==true)return 'unknown';
  return value.loan_available===true ? 'available' : value.loan_available===false ? 'unavailable' : 'unknown';
}

async function checkSearchAvailability(books,params,signal,publish) {
  const controller=new AbortController();
  let timedOut=false;
  const cancel=()=>controller.abort(signal.reason);
  signal?.addEventListener('abort',cancel,{once:true});
  if(signal?.aborted)cancel();
  const timer=setTimeout(()=>{timedOut=true;controller.abort(new DOMException('대출 상태 확인 시간 초과','TimeoutError'));},45000);
  const scope=controller.signal;
  try {
    await Promise.all(books.map(async book=>{
      const summary=book.availability;
      let unavailable=0,unknown=0;
      const apply=(row,value)=>{
        summary.checked++;
        const state=knownLoanState(value);
        if(state==='available') {summary.state='available';summary.availableLibrary=row.name;summary.message=null;}
        else if(state==='unavailable')unavailable++;
        else unknown++;
      };
      try {
        const response=await librarySlot(()=>request(`/libraries/by-book/${book.isbn13}`,new URLSearchParams(params),scope),scope);
        const rows=response.items;
        const district=params.get('district');
        if(!Array.isArray(rows) || !Number.isInteger(response.total) || response.total!==rows.length || !rows.length ||
          new Set(rows.map(row=>row?.library_code)).size!==rows.length ||
          rows.some(row=>typeof row?.library_code!=='string' || !/^[0-9]{1,20}$/.test(row.library_code) ||
            !Object.values(districts).includes(row.district) || (district && row.district!==district))) {
          throw new Error('소장 도서관 목록을 모두 확인하지 못했습니다.');
        }
        summary.total=rows.length;
        const pending=[];
        // 지역 안의 캐시만 확인합니다. 다른 구의 성공 상태를 책 전체 상태로 저장하지 않습니다.
        for(const row of rows) {
          const saved=cached(statusCache,`${book.isbn13}:${row.library_code}`);
          if(saved)apply(row,saved.value);else pending.push(row);
          if(summary.state==='available')break;
        }
        publish();
        if(summary.state==='available')return;
        // 책마다 한 건씩 다음 차례에 줄을 서므로 뒤쪽 책도 함께 확인할 수 있습니다.
        for(const row of pending) {
          scope.throwIfAborted();
          try {apply(row,await availabilityValue(book.isbn13,row.library_code,scope));}
          catch(error) {
            if(scope.aborted)throw error;
            summary.checked++;unknown++;
            summary.message=error.message;
            if(error.status===503 && error.retryAfter>0)break;
          }
          publish();
          if(summary.state==='available')return;
        }
        summary.state=summary.checked===summary.total && unavailable===summary.total && unknown===0 ? 'unavailable' : 'unknown';
        if(summary.state==='unknown' && !summary.message)summary.message='일부 도서관의 대출 상태를 확인하지 못했습니다.';
      } catch(error) {
        if(signal?.aborted)throw error;
        summary.state='unknown';
        summary.message=timedOut ? '확인이 지연되고 있습니다. 소장 도서관 목록에서 다시 확인하세요.' : error.message;
      }
      publish();
    }));
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort',cancel);
  }
}

async function coverURLForBook(book,signal) {
  const saved=cached(bookCache,book.isbn13);
  if(saved?.value.coverUrl)return saved.value.coverUrl;
  if(saved?.coverRetryAt>Date.now())return null;
  return coverSlot(async()=>{
    const existing=cached(bookCache,book.isbn13);
    if(existing?.value.coverUrl)return existing.value.coverUrl;
    if(existing?.coverRetryAt>Date.now())return null;
    if(availabilityBlockedUntil>Date.now())throw availabilityBlockError;
    try {
      const detail=bookModel(await request(`/books/${book.isbn13}`,new URLSearchParams(),signal));
      remember(bookCache,book.isbn13,detail,3600000,{full:true,coverRetryAt:detail.coverUrl ? 0 : Date.now()+60000});
      return detail.coverUrl || null;
    } catch(error) {
      if(signal?.aborted)throw error;
      const entry=cached(bookCache,book.isbn13);
      if(entry)entry.coverRetryAt=Date.now()+60000;
      noteAvailabilityLimit(error);
      throw error;
    }
  },signal);
}

async function checkSearchCovers(books,signal,publish) {
  const controller=new AbortController();
  let timedOut=false;
  const cancel=()=>controller.abort(signal.reason);
  signal?.addEventListener('abort',cancel,{once:true});
  if(signal?.aborted)cancel();
  const timer=setTimeout(()=>{timedOut=true;controller.abort(new DOMException('표지 정보 확인 시간 초과','TimeoutError'));},30000);
  try {
    await Promise.all(books.map(async book=>{
      if(book.coverUrl) {book.coverLoading=false;return;}
      try {book.coverUrl=await coverURLForBook(book,controller.signal);}
      catch(error) {
        if(signal?.aborted)throw error;
        book.coverError=timedOut ? '표지 정보 확인이 지연되고 있습니다.' : error.message;
      }
      book.coverLoading=false;
      publish();
    }));
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort',cancel);
  }
}

export async function searchBooks({query='',district='all',location,signal,isbn13,field='title',page=1,onUpdate,includeAvailability=false,includeCovers=false}={}) {
  signal?.throwIfAborted();
  const params=new URLSearchParams();
  if (district!=='all') {
    if (!districts[district]) throw new Error('대전의 구를 선택해 주세요.');
    params.set('district',districts[district]);
  }
  if (Number.isFinite(location?.latitude) && Number.isFinite(location?.longitude)) {
    params.set('latitude',location.latitude); params.set('longitude',location.longitude);
  }
  // 검색 결과는 책 목록입니다. 첫 책을 임의 선택하지 않습니다.
  if (query.trim() && !isbn13) {
    const search=new URLSearchParams({q:query.trim(),field,page,page_size:10});
    if (district!=='all') search.set('district',districts[district]);
    if (params.has('latitude')) {
      search.set('latitude',params.get('latitude'));search.set('longitude',params.get('longitude'));
      search.set('sort','distance');
    }
    const data=await request('/books/search',search,signal);
    const books=data.items.map(bookModel);
    for(const book of books) {
      const saved=cached(bookCache,book.isbn13);
      if(!book.coverUrl && saved?.value.coverUrl)book.coverUrl=saved.value.coverUrl;
      // 검색에서 확인한 서지를 보관하되, 더 풍부한 상세 응답을 덮어쓰지 않습니다.
      if(!saved?.full)remember(bookCache,book.isbn13,{...book,nearestDistanceKm:null},3600000,{full:false,coverRetryAt:saved?.coverRetryAt || 0});
    }
    const result={book:null,books,holdings:[],total:data.total,page:data.page,pageSize:data.page_size};
    if((!includeAvailability && !includeCovers) || !books.length)return result;
    for(const book of books) {
      if(includeAvailability)book.availability={state:'loading',checked:0,total:null,availableLibrary:null,message:null};
      if(includeCovers)book.coverLoading=!book.coverUrl;
    }
    const snapshot=()=>({...result,books:books.map(book=>({...book,...(book.availability ? {availability:{...book.availability}} : {})}))});
    const publish=()=>{if(!signal?.aborted)onUpdate?.(snapshot());};
    publish();
    await Promise.all([
      includeAvailability ? checkSearchAvailability(books,params,signal,publish) : undefined,
      includeCovers ? checkSearchCovers(books,signal,publish) : undefined,
    ]);
    signal?.throwIfAborted();
    return snapshot();
  }
  if (isbn13 && !/^[0-9]{13}$/.test(isbn13)) throw new Error('올바른 ISBN을 선택해 주세요.');
  const saved=isbn13 ? cached(bookCache,isbn13) : null;
  const result={book:saved?.value || null,holdings:[],total:null,holdingsState:'loading',
    bookLoading:Boolean(isbn13&&!saved?.full),availabilityLoading:false};
  const snapshot=()=>({...result,holdings:result.holdings.map(row=>({...row}))});
  const publish=()=>{if(!signal?.aborted)onUpdate?.(snapshot());};
  const checkAbort=error=>{if(signal?.aborted || error?.name==='AbortError')throw error;};
  publish();

  async function detail() {
    if(!isbn13 || saved?.full)return;
    try {
      const book=bookModel(await request(`/books/${isbn13}`,new URLSearchParams(),signal));
      remember(bookCache,isbn13,book,3600000,{full:true,coverRetryAt:book.coverUrl ? 0 : Date.now()+60000});result.book=book;
    } catch(error) {checkAbort(error);result.bookError=error;}
    finally {result.bookLoading=false;publish();}
  }

  async function availability() {
    if(!isbn13)return;
    const queue=result.holdings.filter(row=>row.statusLoading);
    result.availabilityLoading=queue.length>0;
    publish();
    async function worker() {
      while(queue.length) {
        signal?.throwIfAborted();const holding=queue.shift();
        const locallyBlocked=availabilityBlockedUntil>Date.now();
        try {
          if(locallyBlocked)throw availabilityBlockError;
          const value=await availabilityValue(isbn13,holding.id,signal);
          applyStatus(holding,value);
        } catch(error) {
          checkAbort(error);holding.statusLoading=false;holding.status='unknown';holding.statusError=error.message;
          // 이미 시작한 최대 3건 외의 추가 호출을 멈추고 반복 클릭도 제한합니다.
          if(error.status===503 && error.retryAfter>0) {
            noteAvailabilityLimit(error);
            result.availabilityError=error;
          }
        }
        publish();
      }
    }
    await Promise.all(Array.from({length:Math.min(3,queue.length)},worker));
    result.availabilityLoading=false;publish();
  }

  async function libraries() {
    try {
      const data=await request(isbn13 ? `/libraries/by-book/${isbn13}` : '/libraries',params,signal);
      result.holdings=data.items.map(row=>{
        const holding=libraryModel(row);
        if(isbn13) {
          const status=cached(statusCache,`${isbn13}:${holding.id}`);
          if(status)applyStatus(holding,status.value);else holding.statusLoading=true;
        }
        return holding;
      });
      result.total=data.total;result.holdingsState='ready';publish();
    } catch(error) {
      checkAbort(error);result.holdingsState='error';result.holdingsError=error;publish();return;
    }
    await availability();
  }
  // 상세 조회·소장 목록·대출 조회의 실패 범위를 분리하고 목록부터 표시합니다.
  await Promise.all([detail(),libraries()]);
  signal?.throwIfAborted();return snapshot();
}
