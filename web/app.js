import { getDistricts, searchBooks } from './api.js?v=20261112-list-covers-1';
import { CATALOG_SNAPSHOT_LABEL } from './config.js?v=20261112-catalog-2';
import { connectMap, hasMapPoint, mapMarkup, refreshMap, renderMapPins, updateMapLocationDisplay } from './map.js?v=20261113-status-source-1';
import { distance, escapeHTML as h, icon, statusIcons, statusText, webURL } from './ui.js?v=20261113-status-source-1';
import { officialBookLink } from './official-library.js?v=20261112-official-book-link-2';

const app = document.querySelector('#app');
const dialog = document.querySelector('#info-dialog');
const coverDialog = document.querySelector('#cover-dialog');
const holdingDialog = document.querySelector('#holding-dialog');
let holdingDialogSelection = null;
const districtIcons = { yuseong: 'building', seo: 'city', jung: 'landmark', dong: 'network', daedeok: 'park' };
const help = {
  guide: ['이용안내', '도서명, 저자 또는 키워드로 검색하세요. 검색 결과에서 도서관을 선택하면 소장 위치와 대출 상태를 확인할 수 있습니다.'],
  privacy: ['개인정보처리 안내', '위치 확인을 선택하면 브라우저에 위치 권한을 요청합니다. 서버 연결 모드에서는 거리 계산을 위해 승인된 위치를 검색 서버에 전송합니다.'],
  api: ['도서관 운영 정보 API', '책 검색 API → ISBN 선택 → 소장 도서관 API → 도서관별 대출 상태 API 순서로 연결합니다. 구 이름은 고정 선택지이며, 제공되지 않은 수량이나 서가 정보는 표시하지 않습니다.'],
  contact: ['오류 및 개선 문의', '소장 정보가 실제와 다를 경우 해당 도서관에 문의해 주세요. 전화번호가 제공되면 도서관 카드에서 바로 연결할 수 있습니다.'],
  location: ['위치 허용 방법', 'Chrome 주소창 왼쪽의 사이트 정보 → 사이트 설정 → 위치에서 이 사이트의 위치 접근을 허용해 주세요. Windows 설정 → 개인정보 및 보안 → 위치에서 위치 서비스도 확인하세요. 설정을 바꾼 뒤 화면을 새로고침하고 내 위치 확인을 다시 누르세요.'],
};

let districts = [];
let districtError = false;
let location = null;
let locationState = 'idle';
let locationError = '';
const showCovers = new URLSearchParams(window.location.search).get('covers') !== 'off';
let route = readRoute();
let request;
let data;
let selectedId;
let availableOnly = false;
let libraryFilter = '';
// 화면을 바꿔도 지도 하나를 재사용합니다. 홈에서는 잠시 분리해 둡니다.
let resultsMapPanel;
const bookSummaryViews=new WeakMap();
const bookChoiceViews=new WeakMap(),bookAvailabilityViews=new WeakMap();
const bookCoverViews=new WeakMap();

// 검색 조건을 주소에 보존해 새로고침과 뒤로 가기를 지원합니다.
function readRoute() {
  const params = new URLSearchParams(window.location.search);
  const query = (params.get('q') || '').trim();
  const district = params.get('district') || 'all';
  const field = ['title','author','keyword','publisher','isbn13'].includes(params.get('field')) ? params.get('field') : 'title';
  const page = Number(params.get('page') || 1);
  const isbn13 = /^[0-9]{13}$/.test(params.get('isbn13') || '') ? params.get('isbn13') : undefined;
  return { results: params.get('view') === 'results' || !!query, query, district, field, isbn13,
    page: Number.isInteger(page) && page >= 1 && page <= 1000 ? page : 1 };
}

function districtName(id) {
  return districts.find((district) => district.id === id)?.name || '대전 전체';
}

function districtOptions() {
  const choices = districts.some(({ id }) => id === route.district) || route.district === 'all'
    ? districts : [...districts, { id: route.district, name: route.district }];
  return `<option value="all">대전 전체</option>${choices.map(({ id, name }) =>
    `<option value="${h(id)}"${id === route.district ? ' selected' : ''}>${h(name)}</option>`).join('')}`;
}

function searchForm(compact) {
  return `<form class="search-form search-form--${compact ? 'compact' : 'hero'}" role="search" data-search>
    <label class="district-wrap">
      ${compact ? '' : icon('pin', 18)}
      <select name="district" class="search-district" aria-label="검색 자치구">${districtOptions()}</select>
      ${icon('chevron', 16)}
    </label>
    <select name="field" class="search-field-select" aria-label="검색 항목">${[['title','제목'],['author','저자'],['keyword','키워드'],['publisher','출판사'],['isbn13','ISBN']].map(([value,label]) => `<option value="${value}"${(route.field || 'title')===value ? ' selected' : ''}>${label}</option>`).join('')}</select>
    <label class="search-input-wrap">
      ${compact ? icon('search', 22) : ''}
      <input name="query" type="search" aria-label="도서명, 저자 또는 키워드" maxlength="100" required value="${h(route.query)}"
        placeholder="${compact ? '도서명 또는 저자 검색' : '도서명 또는 저자, 키워드를 입력해보세요 (예: 불편한 편의점)'}">
    </label>
    <button type="submit" class="search-submit">${icon('search', compact ? 18 : 23)} ${compact ? '검색' : '통합 검색'}</button>
  </form>`;
}

function header() {
  const locationLabel = location?.label;
  return `<header class="site-header${route.results ? ' site-header--compact' : ''}">
    <a class="brand" href="./" data-home aria-label="BookRoot 홈">
      <img class="brand-image" src="./assets/bookroot-logo.png" alt="BookRoot">
      <span class="brand-copy">
        ${route.results ? '' : '<span class="brand-tagline">대전 도서관을 잇는 책의 뿌리</span>'}</span>
    </a>
    <div class="header-actions">
      ${`<button class="location-chip" type="button" data-location>
        <span class="location-dot" aria-hidden="true"></span>${icon('navigation', 17)}
        <span>${locationLabel ? `내 위치: ${h(locationLabel)}` : '내 위치 확인'}</span>
      </button>`}
      <button class="help-button" type="button" data-info="guide" aria-label="이용안내">${icon('help', 25)}</button>
    </div>
  </header>`;
}

function footer() {
  return `<footer class="site-footer${route.results ? ' site-footer--compact' : ''}">
    <div class="footer-identity">
      <a class="footer-brand" href="./" data-home aria-label="BookRoot 홈"><img class="footer-logo" src="./assets/bookroot-logo.png" alt="BookRoot"></a>
      <p>© 2026 BookRoot 대전광역시 도서관 소장 도서 검색 서비스.</p>
      <p>장서 기준: ${h(CATALOG_SNAPSHOT_LABEL)} · 국립중앙도서관 도서관 정보나루 · 저작자표시(BY)</p>
    </div>
    <nav class="footer-links" aria-label="서비스 안내">
      <button type="button" data-info="guide">이용안내</button>
      <button type="button" data-info="privacy">개인정보처리방침</button>
      <button type="button" data-info="api">도서관 운영 정보 API</button>
      <button type="button" data-info="contact">오류 및 개선 문의</button>
    </nav>
  </footer>`;
}

function locationStatus() {
  const active = Boolean(location);
  const title = locationState === 'loading' ? '내 위치를 확인하고 있습니다…' : locationState === 'error' ? (active ? '위치 재확인 실패 · 이전 위치 사용 중' : '내 위치 확인 실패') : active ? '내 위치 확인됨' : '내 위치 미확인';
  const accuracy = Number.isFinite(location?.accuracy) ? ` · 측정 오차 약 ${Math.round(location.accuracy)}m` : '';
  const subtitle = locationState === 'loading' ? '브라우저에서 위치 접근을 허용해 주세요.' : locationState === 'error' ? `${locationError}${active ? ' 지도에는 이전에 확인한 위치가 표시됩니다.' : ''}` : active ? `지도에 파란 점과 ‘내 위치’로 표시합니다${accuracy}. 선택한 지역의 소장 도서관을 가까운 순으로 정렬합니다.` : '상단 또는 지도 안의 ‘내 위치 확인’을 누르고 허용하면 가까운 소장 도서관부터 볼 수 있습니다. 현재는 이름순입니다.';
  return `<section class="location-status${active && locationState!=='error' ? ' is-connected' : ''}" data-location-status role="status" aria-live="polite">${icon('locate',21)}<div><strong>${h(title)}</strong><span>${h(subtitle)}</span>${locationState==='error' ? '<button type="button" class="map-location-help" data-info="location">위치 허용 방법</button>' : ''}</div></section>`;
}

function updateLocationDisplay() {
  const bar = app.querySelector('[data-location-status]');
  if (bar) bar.outerHTML = locationStatus();
  const button = app.querySelector('[data-location]');
  if (button) {
    button.disabled = locationState === 'loading';
    button.querySelector('span:last-child').textContent = locationState === 'loading' ? '위치 확인 중…' : locationState==='error' ? '내 위치 다시 확인' : location?.label || '내 위치 확인';
  }
  const panel=app.querySelector('.map-panel');
  if (panel) updateMapLocationDisplay(panel,{phase:locationState,hasLocation:Boolean(location),message:locationError,accuracy:location?.accuracy});
}

// API의 자치구 데이터로 도서관 안내 카드를 만듭니다.
function districtCards() {
  if (districtError) return '<p class="notice">자치구 목록을 불러오지 못했습니다. <button type="button" data-retry-districts>다시 시도</button></p>';
  if (!districts.length) return '<p class="notice" role="status">자치구 목록을 불러오는 중입니다.</p>';
  return districts.map((district) => {
    const nearby = district.id === location?.districtId;
    return `<button class="district-card${nearby ? ' is-nearby' : ''}" type="button" data-district="${h(district.id)}">
      <span class="district-icon">${icon(districtIcons[district.id] || 'building', 23)}</span>
      ${nearby ? '<span class="district-nearby">내 위치</span>' : ''}
      <strong class="district-name">${h(district.name)}</strong>
      <span class="district-count">${Number.isInteger(district.libraryCount) ? `참여 도서관 <strong>${district.libraryCount}곳</strong>` : '지역 선택 후 책 검색'}</span>
      ${district.examples?.length ? `<span class="district-examples">${h(district.examples.join('·'))} 등</span>` : ''}
    </button>`;
  }).join('');
}

function home() {
  const total = districts.reduce((sum, district) => sum + Number(district.libraryCount || 0), 0);
  return `<main class="home-main" id="main">
    <section class="hero" aria-labelledby="home-title">
      <span class="hero-badge">${icon('tree', 18)} <span data-district-total>대전 도서관 소장 도서 검색</span></span>
      <div class="hero-copy">
        <h1 id="home-title">찾으시는 책, 대전 어느 도서관에 있을까요?</h1>
        <p>지역을 선택하고 책을 찾은 뒤, 내 위치에서 가까운 소장 도서관과 대출 가능 여부를 확인하세요.</p>
      </div>
      ${searchForm(false)}
    </section>
    <section class="regional" aria-labelledby="regional-title">
      <p class="section-kicker">REGIONAL ACCESS</p>
      <h2 id="regional-title">대전광역시 자치구별 도서관</h2>
      <div class="district-grid">${districtCards()}</div>
    </section>
  </main>`;
}

function bookSummary(book, holdings) {
  const cover = showCovers ? webURL(book.coverUrl) : '';
  const distances = holdings.map(({ distanceKm }) => distanceKm).filter((km) => Number.isFinite(km) && km >= 0);
  const nearest = distances.length ? distance(Math.min(...distances)) : '';
  const details = [
    ['저자', book.author],
    ['ISBN', book.isbn13],
    ['출판사', book.publisher],
    ['출판연도', book.publicationYear],
    ['출판일', book.publishedAt && book.publishedAt !== book.publicationYear ? book.publishedAt : null],
    ['도서관까지의 거리', nearest],
  ].filter(([, value]) => value);
  return `<div class="book-summary">
    ${cover ? `<button type="button" class="cover-preview-button cover-preview-button--summary" data-cover-open aria-label="${h(book.title)} 표지 크게 보기"><img class="book-cover" src="${cover}" alt="${h(book.title)} 표지" referrerpolicy="no-referrer"><span class="cover-preview-hint">표지 크게 보기</span></button>` : `<div class="book-cover book-cover--empty">${icon('book', 27)}</div>`}
    <div class="book-info">
      <span class="book-badge">도서 정보</span>
      <h1>${h(book.title)}</h1>
      <dl class="book-meta">${details.map(([label, value]) => `<div><dt>${label}</dt><dd>${h(value)}</dd></div>`).join('')}</dl>
    </div>
  </div>`;
}

function libraryCard(holding) {
  const selected = holding.id === selectedId;
  const km = distance(holding.distanceKm);
  const status = holding.status;
  const directions = webURL(holding.directionsUrl);
  const shelf = webURL(holding.shelfUrl);
  const official = route.isbn13 ? officialBookLink(route.isbn13, data?.book?.title, holding) : null;
  const phone = holding.phone?.replace(/[^+\d]/g, '');
  const title = h(holding.name);
  const statusChip = holding.statusLoading ? `<span class="status-chip" data-status="unknown">${icon('clock',16)} 확인 중</span>` : status ? `<span class="status-chip" data-status="${h(status)}">
    ${icon(statusIcons[status] || 'help', 16)} ${h(statusText(holding))}</span>` : '';
  return `<article class="library-card${selected ? ' is-selected' : ''}" data-library-card="${h(holding.id)}">
    ${selected && hasMapPoint(holding) ? `<span class="map-selected-label">${icon('pin', 14)} 선택한 도서관</span>` : ''}
    <div class="library-heading">
      <div class="library-name-group">
        <h3 class="library-name"><button type="button" data-library="${h(holding.id)}" aria-pressed="${selected}">${title}</button></h3>
        ${holding.neighborhood ? `<span class="library-neighborhood">${h(holding.neighborhood)}</span>` : ''}
      </div>
      ${statusChip}
    </div>
    ${km ? `<p class="library-distance">${selected ? icon('ruler', 16) : ''} 내 위치에서 <strong>${km}</strong>${selected ? ' <span>(직선거리)</span>' : ''}</p>` : ''}
    ${selected ? `<div class="library-details">
      ${holding.room || holding.hours ? `<div class="detail-row">
        ${holding.room ? `<span>위치: <strong>${h(holding.room)}</strong></span>` : '<span></span>'}
        ${holding.hours ? `<span>운영: <strong>${h(holding.hours)}</strong></span>` : ''}
      </div>` : ''}
      ${holding.callNumber || directions ? `<div class="detail-row">
        ${holding.callNumber ? `<span>청구기호: <code>${h(holding.callNumber)}</code></span>` : '<span></span>'}
        ${shelf ? `<a href="${shelf}" target="_blank" rel="noopener noreferrer">서가배치도</a>` :
          holding.room && holding.callNumber ? `<button class="text-button" type="button" data-shelf="${h(holding.id)}">서가 위치</button>` :
          directions ? `<a href="${directions}" target="_blank" rel="noopener noreferrer">길안내</a>` : ''}
      </div>` : ''}
    </div>` : ''}
    ${!selected && (holding.room || holding.callNumber) ? `<div class="library-extra">
      <span>${holding.room ? `자료실: ${h(holding.room)}` : `청구기호: ${h(holding.callNumber)}`}</span>
      ${holding.room && holding.callNumber ? `<code>${h(holding.callNumber)}</code>` : ''}
      ${Number.isInteger(holding.waitCount) ? `<small>예약 대기자: ${holding.waitCount}명</small>` : ''}
    </div>` : ''}
    ${status === 'unknown' ? `<p class="library-unknown">${h(holding.statusError || '대출 상태는 도서관에 문의해 주세요.')}</p>` : ''}
    ${selected && webURL(holding.homepage) ? `<p class="library-contact"><a href="${webURL(holding.homepage)}" target="_blank" rel="noopener noreferrer">도서관 홈페이지 ↗</a></p>` : ''}
    ${phone ? `<div class="library-contact"><a href="tel:${h(phone)}">${icon('phone', 15)} ${h(holding.phone)} 문의</a></div>` : ''}
    ${route.isbn13 ? `<div class="official-book-action">
      ${official ? `<a class="holding-card-button" href="${official.href}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">공식 사이트에서 현재 상태 확인 ↗</a>` : ''}
      <button type="button" class="holding-card-button" data-holding-open="${h(holding.id)}" aria-haspopup="dialog" aria-controls="holding-dialog"
        aria-label="${title} 소장·대출 정보 보기">소장·대출 정보 보기 ${icon('info',16)}</button>
    </div>` : ''}
  </article>`;
}

function filteredHoldings() {
  const filter = libraryFilter.toLowerCase().replace(/\s/g, '');
  return data.holdings.filter((holding) =>
    (!availableOnly || holding.status === 'available')
    && holding.name.toLowerCase().replace(/\s/g, '').includes(filter));
}

// 필터가 바뀌면 목록, 소장 수, 지도 핀을 함께 갱신합니다.
function updateHoldings() {
  if(data.holdingsState && data.holdingsState!=='ready')return;
  const holdings = filteredHoldings();
  const focusedLibrary=document.activeElement?.closest('[data-library]')?.dataset.library;
  if (!holdings.some((holding) => holding.id === selectedId)) selectedId = holdings[0]?.id;
  app.querySelector('.holdings-count').textContent = `총 ${data.total ?? data.holdings.length}곳${holdings.length !== data.holdings.length ? ` · ${holdings.length}곳 표시` : ''}`;
  app.querySelector('.holdings-list').innerHTML = holdings.length ? holdings.map(libraryCard).join('') :
    `<p class="empty-state">${data.availabilityLoading && availableOnly ? '대출 상태를 확인하고 있습니다. 확인된 결과부터 표시합니다.' : data.holdings.length ? '조건에 맞는 도서관이 없습니다. 미확인 도서관도 보려면 대출 가능 필터를 해제해 주세요.' :
      route.query && !data.book ? '검색 결과가 없습니다. 다른 도서명이나 저자로 검색해 보세요.' : '표시할 도서관이 없습니다.'}</p>`;
  renderMapPins(app.querySelector('.map-panel'), holdings, selectedId, location);
  if(focusedLibrary) [...app.querySelectorAll('[data-library]')].find(node=>node.dataset.library===focusedLibrary)?.focus({preventScroll:true});
}

function mapTitle() {
  return route.district === 'all' ? '대전광역시' : `대전광역시 ${districtName(route.district)}`;
}

function results() {
  return `<div class="results-searchbar">${searchForm(true)}</div>
    <p class="catalog-source-note">장서 목록은 ${h(CATALOG_SNAPSHOT_LABEL)} 공개 자료입니다. 각 도서관의 ‘소장·대출 정보 보기’에서 조회 정보를 확인하세요. 현재 대출 상태는 공식 도서관 사이트를 우선 확인하세요. 아래 정보나루 상태는 전날 기준 참고 정보이며 실제와 다를 수 있습니다.</p>
    <main id="main" class="results-main">
      <section class="results-sidebar" aria-label="도서 및 소장 도서관">
        <div class="results-summary">
          <div data-book-summary></div>
          <div class="holdings-title"><h2>${route.query ? '소장 도서관' : `${h(districtName(route.district))} 도서관`}</h2>
            <span class="holdings-count" aria-live="polite"></span>
          </div>
          <div class="holdings-toolbar">
            ${route.query ? `<button type="button" class="available-toggle" data-available aria-pressed="false">${icon('check', 15)} 정보나루 가능만 보기 (전날)</button>` : ''}
            <label class="library-filter">${icon('search', 16)}
              <input type="search" aria-label="도서관명 검색" placeholder="도서관명 검색" maxlength="100">
            </label>
            <a class="mobile-map-link" href="#holdings-map">지도 보기</a>
          </div>
          <p class="book-sort-note" data-book-sort hidden></p>
          <p class="notice" data-result-status role="status" aria-live="polite" hidden></p>
        </div>
        <div class="holdings-list" tabindex="0" aria-label="소장 도서관 목록" aria-busy="true">
          <p class="notice" role="status">도서관 정보를 불러오는 중입니다.</p>
        </div>
      </section>
      ${mapMarkup(mapTitle(), route.district === 'yuseong' ? 'YUSEONG-GU DISTRICT HOLDINGS' : 'DAEJEON LIBRARY HOLDINGS')}
    </main>`;
}

function render() {
  app.innerHTML = `<div class="app-shell${route.results ? ' app-shell--results' : ''}">
    ${header()}${locationStatus()}${route.results ? results() : home()}${footer()}
  </div>`;
  document.title = route.results ? '검색 결과 | BookRoot' : 'BookRoot | 대전 공공도서관 통합 검색';
  if (route.results) {
    const placeholder = app.querySelector('.map-panel');
    if (resultsMapPanel) placeholder.replaceWith(resultsMapPanel);
    else {
      resultsMapPanel = placeholder;
      connectMap(resultsMapPanel, locate);
    }
    refreshMap(resultsMapPanel, mapTitle(), route.district === 'yuseong' ? 'YUSEONG-GU DISTRICT HOLDINGS' : 'DAEJEON LIBRARY HOLDINGS');
    // 새 책을 불러오는 동안 이전 책의 도서관 핀을 남기지 않습니다.
    renderMapPins(resultsMapPanel, [], undefined, location);
  }
  updateLocationDisplay();
}

function bookAvailabilityMarkup(availability) {
  const state=availability?.state || 'loading';
  const label={available:'정보나루: 대출 가능 · 전날',unavailable:'정보나루: 대출 불가 · 전날',unknown:'대출 여부 미확인',loading:'대출 여부 확인 중'}[state];
  const status=state==='loading' ? 'unknown' : state;
  let note;
  if(state==='available')note=`${availability.availableLibrary || '선택 지역의 도서관'}에서 가능 · 전날 기준`;
  else if(state==='unavailable')note=`${districtName(route.district)} 소장 도서관 ${availability.total}곳 확인 · 전날 기준`;
  else if(state==='unknown')note=availability.message || '소장 도서관 목록에서 상태를 다시 확인하세요.';
  else note=availability?.total ? `${availability.checked}/${availability.total}개 도서관 확인 중` : '선택 지역의 소장 도서관을 확인하고 있습니다.';
  return `<span class="status-chip" data-status="${status}">${icon(state==='loading' ? 'clock' : statusIcons[status] || 'help',15)} ${h(label)}</span><small>${h(note)}</small>`;
}

function updateBookAvailability(books) {
  const byIsbn=new Map(books.map(book=>[book.isbn13,book.availability]));
  for(const node of app.querySelectorAll('[data-book-availability]')) {
    const markup=bookAvailabilityMarkup(byIsbn.get(node.dataset.bookAvailability));
    if(bookAvailabilityViews.get(node)!==markup) {node.innerHTML=markup;bookAvailabilityViews.set(node,markup);}
  }
}

function choiceCoverPlaceholder(book,message) {
  return `<span class="choice-placeholder" role="img" aria-label="${h(book.title)} ${h(message)}" title="${h(message)}">${icon('book',30)}</span>`;
}

function updateBookCovers(books) {
  const byIsbn=new Map(books.map(book=>[book.isbn13,book]));
  for(const node of app.querySelectorAll('[data-book-cover]')) {
    const book=byIsbn.get(node.dataset.bookCover);
    if(!book)continue;
    const source=showCovers ? webURL(book.coverUrl) : '';
    const previous=bookCoverViews.get(node);
    if(source) {
      // 실패한 URL도 같은 화면의 대출 갱신 때마다 다시 요청하지 않습니다.
      if(previous?.source===source)continue;
      node.innerHTML=`<button type="button" class="cover-preview-button cover-preview-button--choice" data-cover-open aria-label="${h(book.title)} 표지 크게 보기"><img class="choice-cover" src="${source}" alt="${h(book.title)} 표지" loading="lazy" referrerpolicy="no-referrer"></button>`;
      bookCoverViews.set(node,{source});
      node.querySelector('img').addEventListener('error',()=>{
        node.innerHTML=choiceCoverPlaceholder(book,'표지를 불러오지 못했습니다.');
      },{once:true});
    } else {
      const message=book.coverError ? '표지를 불러오지 못했습니다.' : showCovers && book.coverLoading ? '표지 확인 중' : '표지 미제공';
      if(previous?.source==='' && previous.message===message)continue;
      node.innerHTML=choiceCoverPlaceholder(book,message);
      bookCoverViews.set(node,{source:'',message});
    }
  }
}

function bookChoices(response) {
  app.querySelector('.holdings-title h2').textContent = '도서 검색 결과';
  app.querySelector('.holdings-count').textContent = `총 ${response.total}권`;
  const sortNote=app.querySelector('[data-book-sort]');
  sortNote.hidden=false;
  sortNote.textContent=location ? '가장 가까운 소장 도서관까지의 직선거리순입니다. 도서관 좌표가 없는 책은 뒤에 표시합니다.' : '제목 일치도를 먼저 표시합니다. 내 위치를 확인하면 책 목록도 가까운 소장 도서관순으로 정렬합니다.';
  const toggle=app.querySelector('[data-available]'); if (toggle) toggle.hidden=true;
  app.querySelector('.library-filter').hidden=true;
  const list=app.querySelector('.holdings-list');
  // 표지·대출 응답만 갱신될 때는 카드와 선택 버튼을 그대로 유지합니다.
  const view=JSON.stringify(response.books.map(({availability,coverUrl,coverLoading,coverError,...book})=>book));
  list.setAttribute('aria-busy','false');
  if(bookChoiceViews.get(list)===view) {updateBookAvailability(response.books);updateBookCovers(response.books);return;}
  const books=response.books.map(book => `<article class="library-card book-choice">
    <div class="choice-cover-slot" data-book-cover="${h(book.isbn13)}"></div>
    <div><h3>${h(book.title)}</h3><p>${h(book.author || '저자 미제공')}</p><p>${h(book.publisher)} · ${h(book.publicationYear || '출판연도 미제공')}</p>
    <p>${book.libraryCount}개 도서관 소장</p>
    ${location ? `<p class="book-nearest-distance">${Number.isFinite(book.nearestDistanceKm) && book.nearestDistanceKm>=0 ? `가장 가까운 소장 도서관 <strong>${distance(book.nearestDistanceKm)}</strong> · 직선거리` : '소장 도서관 좌표 미제공'}</p>` : ''}
    <div class="book-loan-status" data-book-availability="${h(book.isbn13)}" role="status" aria-live="polite"></div>
    <button class="choose-book" type="button" data-book="${h(book.isbn13)}">소장 도서관 보기 →</button></div></article>`).join('');
  list.innerHTML = books || '<p class="empty-state">선택한 구에 검색 결과가 없습니다.</p>';
  const pages=Math.max(1,Math.ceil(response.total/response.pageSize));
  if (pages>1) list.insertAdjacentHTML('beforeend',`<nav class="book-pages" aria-label="도서 검색 페이지"><button data-page="${response.page-1}"${response.page<=1?' disabled':''}>이전</button><span>${response.page} / ${pages}</span><button data-page="${response.page+1}"${response.page>=pages?' disabled':''}>다음</button></nav>`);
  bookChoiceViews.set(list,view);
  updateBookAvailability(response.books);
  updateBookCovers(response.books);
  renderMapPins(app.querySelector('.map-panel'),[],undefined,location);
}

function renderResultSnapshot(response) {
  data=response;
  updateHoldingDialog();
  if(Array.isArray(response.books)) {bookChoices(response);return;}
  const summary=app.querySelector('[data-book-summary]');
  const summaryMarkup=response.book ? `<button type="button" class="back-books" data-back-books>← 책 검색 결과</button>${bookSummary(response.book,response.holdings)}` : '';
  // 상태 한 건이 갱신될 때마다 표지와 책 선택 버튼을 다시 만들지 않습니다.
  if(bookSummaryViews.get(summary)!==summaryMarkup) {summary.innerHTML=summaryMarkup;bookSummaryViews.set(summary,summaryMarkup);}
  const notices=[];
  if(response.bookLoading)notices.push('책 상세 정보를 확인하고 있습니다.');
  if(response.bookError)notices.push(`책 상세 조회: ${response.bookError.message}${response.book ? ' 검색에서 확인한 서지 정보로 표시합니다.' : ''}`);
  if(response.availabilityLoading)notices.push('대출 가능 여부를 도서관별로 확인하고 있습니다. 목록은 먼저 이용할 수 있습니다.');
  if(response.availabilityError)notices.push(`대출 상태 조회: ${response.availabilityError.message}`);
  const status=app.querySelector('[data-result-status]');
  status.textContent=notices.join(' ');status.hidden=!notices.length;
  const list=app.querySelector('.holdings-list');
  if(response.holdingsState==='error') {
    app.querySelector('.holdings-count').textContent='확인 필요';
    list.innerHTML=`<p class="notice" role="alert">소장 도서관 조회: ${h(response.holdingsError.message)} <button type="button" data-retry>다시 시도</button></p>`;
    renderMapPins(app.querySelector('.map-panel'),[],undefined,location);
  } else if(response.holdingsState==='loading') {
    app.querySelector('.holdings-count').textContent='조회 중';
    list.innerHTML='<p class="notice" role="status">소장 도서관 정보를 확인하고 있습니다.</p>';
  } else updateHoldings();
  list.setAttribute('aria-busy',String(response.holdingsState==='loading'));
}

// 이전 검색을 취소해 늦게 도착한 응답이 화면을 덮어쓰지 않게 합니다.
async function loadResults() {
  request?.abort();
  const current = new AbortController();
  request = current;
  const list = app.querySelector('.holdings-list');
  const summary = app.querySelector('[data-book-summary]');
  list.setAttribute('aria-busy', 'true');
  try {
    const response = await searchBooks({ ...route, location, signal: current.signal,includeAvailability:true,includeCovers:showCovers,
      onUpdate(snapshot) {if(!current.signal.aborted && request===current)renderResultSnapshot(snapshot);},
    });
    if (current.signal.aborted) return;
    renderResultSnapshot(response);
  } catch (error) {
    if (!current.signal.aborted) {
      data = undefined;
      summary.replaceChildren();
      app.querySelector('.holdings-count').textContent = '확인 필요';
      renderMapPins(app.querySelector('.map-panel'), [], undefined, location);
      list.innerHTML = `<p class="notice" role="alert">${h(error.message)} <button type="button" data-retry>다시 시도</button></p>`;
    }
  } finally {
    if (!current.signal.aborted) list.setAttribute('aria-busy', 'false');
  }
}

// 검색과 자치구 이동에 동일한 결과 화면을 사용합니다.
function transition(nextRoute, push = true) {
  if (holdingDialog.open) holdingDialog.close();
  route = nextRoute;
  request?.abort();
  data = undefined;
  selectedId = undefined;
  availableOnly = false;
  libraryFilter = '';
  if (push) {
    const url = new URL('./', window.location.href);
    if (route.results) {
      url.search = new URLSearchParams({ view: 'results', q: route.query, district: route.district, field:route.field || 'title', page:route.page || 1 });
      if (route.isbn13) url.searchParams.set('isbn13',route.isbn13);
    }
    if (!showCovers) url.searchParams.set('covers','off');
    history.pushState(null, '', url);
  }
  render();
  if (route.results) loadResults();
  if (push) window.scrollTo(0, 0);
}

async function loadDistricts() {
  districtError = false;
  try {
    districts = await getDistricts();
  } catch {
    districtError = true;
  }
  const select = app.querySelector('.search-district');
  const previous = select.value;
  select.innerHTML = districtOptions();
  if ([...select.options].some(({ value }) => value === previous)) select.value = previous;
  if (route.results) {
    app.querySelector('.map-title strong').textContent = mapTitle();
    if (!route.query) app.querySelector('.holdings-title h2').textContent = `${districtName(route.district)} 도서관`;
  } else {
    app.querySelector('.district-grid').innerHTML = districtCards();
    const total = districts.reduce((sum, district) => sum + Number(district.libraryCount || 0), 0);
    if (total) app.querySelector('[data-district-total]').textContent = `대전 ${total}개 시·구립 공공도서관 통합 검색`;
  }
}

function showInfo(title, message) {
  dialog.querySelector('#info-title').textContent = title;
  dialog.querySelector('#info-content').textContent = message;
  if (!dialog.open) dialog.showModal();
}

function showCover(control) {
  if (!showCovers) return;
  const thumbnail = control.querySelector('img');
  const source = webURL(thumbnail?.getAttribute('src'));
  if (!source) return;
  coverDialog.querySelector('#cover-title').textContent = thumbnail.alt;
  const content = coverDialog.querySelector('[data-cover-content]');
  // 원본 URL을 브라우저에 그대로 표시합니다. 표지 파일은 저장하지 않습니다.
  content.innerHTML = `<img class="cover-preview-image" src="${source}" alt="${h(thumbnail.alt)} 확대" referrerpolicy="no-referrer"><p class="cover-preview-error" role="status" hidden>표지를 불러오지 못했습니다. 잠시 후 다시 눌러 주세요.</p>`;
  content.querySelector('img').addEventListener('error', event => {
    event.currentTarget.remove();
    content.querySelector('[role="status"]').hidden = false;
  }, {once:true});
  if (!coverDialog.open) coverDialog.showModal();
}

coverDialog.addEventListener('close', () => coverDialog.querySelector('[data-cover-content]').replaceChildren());

function updateHoldingDialog() {
  const selection=holdingDialogSelection;
  if (!selection) return;
  const holding=data?.holdings?.find(row=>row.id===selection.libraryId);
  if (route.isbn13!==selection.isbn13 || !holding) {
    holdingDialog.close();
    return;
  }
  const book=data.book;
  const values={
    title:book?.title || '도서 정보를 확인하고 있습니다.',
    author:book?.author || '미제공',publisher:book?.publisher || '미제공',
    year:book?.publicationYear || '미제공',isbn:selection.isbn13,
    library:holding.name,address:holding.neighborhood || '주소 미제공',
    room:holding.room || '자료실 미제공',shelf:holding.shelf || '서가 미제공',
    callNumber:holding.callNumber || '미제공',registration:holding.registrationNumber || '미제공',
  };
  for (const [key,value] of Object.entries(values)) {
    holdingDialog.querySelector(`[data-holding-field="${key}"]`).textContent=value;
  }
  const chip=holdingDialog.querySelector('[data-holding-status]');
  chip.textContent=holding.statusLoading ? '확인 중' : statusText(holding);
  chip.dataset.status=holding.statusLoading ? 'unknown' : holding.status || 'unknown';
  const error=holdingDialog.querySelector('[data-holding-error]');
  error.textContent=holding.statusError || '';
  error.hidden=!holding.statusError;
  const official=officialBookLink(selection.isbn13,book?.title,holding);
  const link=holdingDialog.querySelector('[data-holding-official]');
  link.hidden=!official;
  if (official) link.setAttribute('href',official.href.replaceAll('&amp;','&'));
  else link.removeAttribute('href');
}

function showHoldingDialog(libraryId) {
  if (!route.isbn13 || !data?.holdings?.some(row=>row.id===libraryId)) return;
  holdingDialogSelection={libraryId,isbn13:route.isbn13};
  updateHoldingDialog();
  if (!holdingDialog.open) holdingDialog.showModal();
}

holdingDialog.addEventListener('close',()=>{
  const selection=holdingDialogSelection;
  holdingDialogSelection=null;
  if (selection?.isbn13===route.isbn13) {
    [...app.querySelectorAll('[data-holding-open]')].find(button=>button.dataset.holdingOpen===selection.libraryId)?.focus({preventScroll:true});
  }
});

// 위치 권한은 사용자가 직접 위치 확인을 누를 때만 요청합니다.
function locate() {
  if (!navigator.geolocation) {
    showInfo('내 위치', '이 브라우저에서 위치를 확인할 수 없습니다.');
    return;
  }
  if (!window.isSecureContext) { showInfo('내 위치','위치 확인은 HTTPS 또는 localhost에서 사용할 수 있습니다.'); return; }
  if (locationState === 'loading') return;
  locationState = 'loading'; locationError = ''; updateLocationDisplay();
  navigator.geolocation.getCurrentPosition(({ coords }) => {
    location = { latitude: coords.latitude, longitude: coords.longitude, accuracy:coords.accuracy, label: `현재 위치 · 오차 약 ${Math.round(coords.accuracy)}m` };
    locationState = 'ready'; updateLocationDisplay();
    if (route.results) {
      if (route.query && !route.isbn13) {
        route={...route,page:1};
        const url=new URL(window.location.href);url.searchParams.set('page','1');
        history.replaceState(null,'',url);
      }
      loadResults();
    }
  }, (error) => {
    locationState = 'error';
    locationError = error.code === 1 ? '위치 권한이 거부되었습니다. 브라우저의 사이트 권한과 Windows 위치 설정을 확인해 주세요. 위치 없이도 이름순으로 이용할 수 있습니다.' : error.code === 3 ? '위치 확인 시간이 초과되었습니다. 다시 시도해 주세요.' : '기기에서 위치를 확인하지 못했습니다. Windows 위치 서비스를 확인해 주세요.';
    updateLocationDisplay();
  }, { enableHighAccuracy:true, timeout:15000, maximumAge:30000 });
}

// 지도 핀과 목록을 동기화하고 키보드 포커스를 복원합니다.
function selectLibrary(id, fromMap) {
  if (!data) return;
  selectedId = id;
  updateHoldings();
  const card = [...app.querySelectorAll('[data-library-card]')].find((element) => element.dataset.libraryCard === id);
  if (fromMap) {
    const pin = [...app.querySelectorAll('[data-pin]')].find((element) => element.dataset.pin === id);
    pin?.focus({ preventScroll: true });
    const list = app.querySelector('.holdings-list');
    if (card) list.scrollTop += card.getBoundingClientRect().top - list.getBoundingClientRect().top - 16;
  } else {
    card?.querySelector('[data-library]')?.focus({ preventScroll: true });
  }
}

app.addEventListener('submit', (event) => {
  if (!event.target.matches('[data-search]')) return;
  event.preventDefault();
  const values = new FormData(event.target);
  const query = values.get('query').trim();
  if (!query) {
    const input = event.target.elements.query;
    input.setCustomValidity('도서명 또는 저자를 입력해 주세요.');
    input.reportValidity();
    return;
  }
  transition({ results: true, query, district: values.get('district'), field:values.get('field'), page:1 });
});

app.addEventListener('input', (event) => {
  if (event.target.name === 'query') event.target.setCustomValidity('');
  if (!event.target.closest('.library-filter')) return;
  libraryFilter = event.target.value;
  if (data) updateHoldings();
});

app.addEventListener('click', (event) => {
  const control = event.target.closest('button, a');
  if (!control) {
    const card = event.target.closest('[data-library-card]');
    if (card) selectLibrary(card.dataset.libraryCard, false);
    return;
  }
  const { district, info, library, pin, shelf } = control.dataset;
  if (control.dataset.holdingOpen) { showHoldingDialog(control.dataset.holdingOpen); return; }
  if (control.hasAttribute('data-cover-open')) { showCover(control); return; }
  if (control.dataset.book) { transition({...route,isbn13:control.dataset.book}); return; }
  if (control.hasAttribute('data-back-books')) { transition({...route,isbn13:undefined}); return; }
  if (control.dataset.page) { transition({...route,isbn13:undefined,page:Number(control.dataset.page)}); return; }
  if (control.hasAttribute('data-home')) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (route.results) transition({ results: false, query: '', district: 'all' });
  } else if (info) showInfo(...help[info]);
  else if (control.hasAttribute('data-location')) locate();
  else if (district) transition({ results: true, query: '', district });
  else if (library || pin) selectLibrary(library || pin, !!pin);
  else if (shelf) {
    const holding = data.holdings.find(({ id }) => id === shelf);
    showInfo(`${holding.name} 서가 위치`, `${holding.room} · 청구기호 ${holding.callNumber}`);
  } else if (control.hasAttribute('data-available')) {
    availableOnly = !availableOnly;
    control.setAttribute('aria-pressed', String(availableOnly));
    if (data) updateHoldings();
  } else if (control.hasAttribute('data-retry')) loadResults();
  else if (control.hasAttribute('data-retry-districts')) loadDistricts();
});

window.addEventListener('popstate', () => transition(readRoute(), false));
app.addEventListener('libraryselect',event => selectLibrary(event.detail.id,true));
transition(route, false);
loadDistricts();
