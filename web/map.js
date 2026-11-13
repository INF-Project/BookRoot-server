import { distance,escapeHTML as h,icon,statusText,webURL } from './ui.js?v=20261113-ui-restore-1';
const panels=new WeakMap(); let sdkPromise;

export function hasMapPoint(item) {
  return Number.isFinite(item?.latitude) && Number.isFinite(item?.longitude)
    && Math.abs(item.latitude)<=90 && Math.abs(item.longitude)<=180;
}

function ensureSDK() {
  if (window.L) return Promise.resolve();
  if (!sdkPromise) sdkPromise=new Promise((resolve,reject)=>{
    if (!document.querySelector('link[data-leaflet-css]')) {
      const css=document.createElement('link'); css.rel='stylesheet'; css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'; css.dataset.leafletCss=''; document.head.append(css);
    }
    const script=document.createElement('script'); script.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    let settled=false;
    const finish=error=>{
      if(settled)return;settled=true;clearTimeout(timer);script.onload=null;script.onerror=null;
      if(error) {script.remove();reject(error);} else resolve();
    };
    const timer=setTimeout(()=>finish(new Error('지도 로딩 시간이 초과되었습니다. 다시 시도해 주세요.')),15000);
    script.onload=()=>finish(window.L ? null : new Error('지도 기능을 불러오지 못했습니다. 다시 시도해 주세요.'));
    script.onerror=()=>finish(new Error('지도를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.'));
    document.head.append(script);
  }).catch(error=>{sdkPromise=null;throw error;});
  return sdkPromise;
}

export function mapMarkup(title,subtitle) {
  return `<section class="map-panel live-map-panel" id="holdings-map" aria-label="도서관 위치 지도">
    <div class="map-viewport"><div class="real-map" hidden></div>
    <div class="map-welcome"><div class="map-title"><strong>${h(title)}</strong><span>${h(subtitle)}</span></div>
    <p data-map-description>도서관 지도를 불러오고 있습니다.</p><button type="button" class="choose-book" data-map-open disabled>지도 불러오는 중…</button><p data-map-error role="status"></p></div></div>
    <div class="map-location-controls" aria-label="내 위치 확인과 권한 안내">
      <button type="button" class="map-location-button" data-map-action="locate">${icon('locate',22)}<span data-map-location-label>내 위치 확인</span></button>
      <p class="map-location-status" data-map-location-status role="status" aria-live="polite">위치를 허용하면 가까운 도서관부터 표시합니다.</p>
      <button type="button" class="map-location-help" data-map-location-help aria-expanded="false" aria-controls="map-location-guide">위치 허용 방법</button>
      <div class="map-location-guide" id="map-location-guide" data-map-location-guide hidden>
        <strong>위치 접근이 차단되어 있나요?</strong>
        <ol><li>Chrome 주소창 왼쪽의 사이트 정보 → 사이트 설정에서 <b>위치를 허용</b>하세요.</li><li>Windows 설정 → 개인정보 및 보안 → 위치에서 <b>위치 서비스</b>도 켜져 있는지 확인하세요.</li><li>화면을 새로고침한 후 <b>내 위치 확인</b>을 다시 누르세요.</li></ol>
        <p>권한은 직접 변경해야 합니다. 위치를 허용하지 않아도 도서관 목록은 이름순으로 이용할 수 있습니다.</p>
        <a href="https://support.google.com/chrome/answer/142065?hl=ko" target="_blank" rel="noopener noreferrer">Chrome 위치 권한 안내 ↗</a>
      </div>
    </div>
    <div class="map-note">${icon('info',22)}<span>위치 허용 시 직선거리순으로 정렬합니다. 좌표 없는 도서관은 목록에서 확인하세요.</span></div></section>`;
}

export function connectMap(panel,onLocate) {
  if(panels.has(panel))return;
  const state={holdings:[],selectedId:null,location:null,map:null,layer:null,user:null,fit:true,opening:null,failed:false}; panels.set(panel,state);
  panel.addEventListener('click',event=>{
    if (event.target.closest('[data-map-location-help]')) {
      const guide=panel.querySelector('[data-map-location-guide]');
      guide.hidden=!guide.hidden;
      panel.querySelector('[data-map-location-help]').setAttribute('aria-expanded',String(!guide.hidden));
      return;
    }
    if (event.target.closest('[data-map-action="locate"]')) {onLocate();return;}
    if(event.target.closest('[data-map-open]'))openMap(panel,state);
  });
  openMap(panel,state);
}

function openMap(panel,state) {
  if(state.opening)return state.opening;
  state.opening=(async()=>{
    const button=panel.querySelector('[data-map-open]');
    const welcome=panel.querySelector('.map-welcome');
    const realMap=panel.querySelector('.real-map');
    button.disabled=true;
    button.textContent='지도 불러오는 중…';
    panel.setAttribute('aria-busy','true');
    panel.querySelector('[data-map-description]').textContent='도서관 지도를 불러오고 있습니다.';
    panel.querySelector('[data-map-error]').textContent='';
    state.failed=false;
    try {
      await ensureSDK(); if (!panel.isConnected) return;
      realMap.hidden=false;
      if (!state.map) {
        state.map=L.map(realMap,{zoomControl:false,fadeAnimation:false});
        state.map.setView([36.35,127.38],12);
        L.control.zoom({position:'topright'}).addTo(state.map);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,
          attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'})
          .on('tileerror',()=>{panel.querySelector('.map-note span').textContent='지도 배경을 불러오지 못했습니다. 도서관 목록을 이용해 주세요.';}).addTo(state.map);
        state.layer=L.layerGroup().addTo(state.map);
      }
      state.map.invalidateSize(); draw(panel,state);
      welcome.hidden=true;
    } catch(error) {
      try {state.map?.remove();} catch {}
      state.map=null;state.layer=null;state.user=null;state.fit=true;state.failed=true;
      realMap.hidden=true;welcome.hidden=false;
      panel.querySelector('[data-map-description]').textContent='지도를 불러오지 못했습니다. 다시 시도해 주세요.';
      panel.querySelector('[data-map-error]').textContent=error.message;
    } finally {
      button.disabled=false;button.textContent=state.failed ? '지도 다시 시도' : '지도 보기';
      panel.setAttribute('aria-busy','false');
      state.opening=null;
    }
  })();
  return state.opening;
}

// 같은 지도 DOM을 검색 화면에 다시 붙인 뒤 크기와 지역 안내만 갱신합니다.
export function refreshMap(panel,title,subtitle) {
  panel.querySelector('.map-title strong').textContent=title;
  panel.querySelector('.map-title span').textContent=subtitle;
  requestAnimationFrame(()=>{
    if (!panel.isConnected)return;
    const state=panels.get(panel);
    state?.map?.invalidateSize({pan:false});
    if(state && !state.map && !state.opening && !state.failed)openMap(panel,state);
  });
}

// 헤더와 지도 버튼이 같은 위치 요청 상태를 표시합니다.
export function updateMapLocationDisplay(panel,{phase='idle',hasLocation=false,message='',accuracy}) {
  const state=panels.get(panel); if (!state) return;
  const controls=panel.querySelector('.map-location-controls');
  const button=panel.querySelector('[data-map-action="locate"]');
  const guide=panel.querySelector('[data-map-location-guide]');
  const help=panel.querySelector('[data-map-location-help]');
  button.disabled=phase==='loading';
  controls.dataset.state=phase;
  panel.querySelector('[data-map-location-label]').textContent=phase==='loading' ? '위치 확인 중…' : hasLocation || phase==='error' ? '내 위치 다시 확인' : '내 위치 확인';
  const measured=Number.isFinite(accuracy) ? ` · 오차 약 ${Math.round(accuracy)}m` : '';
  panel.querySelector('[data-map-location-status]').textContent=phase==='loading' ? '브라우저에서 위치 접근을 허용해 주세요.' :
    phase==='error' ? `${message}${hasLocation ? ' 파란 점은 이전에 확인한 위치입니다.' : ''}` :
    hasLocation ? `내 위치 확인됨${measured}. 가까운 순으로 정렬합니다.` : '위치를 허용하면 가까운 도서관부터 표시합니다.';
  if (phase==='error' && state.locationPhase!=='error') {
    guide.hidden=false; help.setAttribute('aria-expanded','true');
  } else if (phase==='ready') {
    guide.hidden=true; help.setAttribute('aria-expanded','false');
  }
  state.locationPhase=phase;
}

export function renderMapPins(panel,holdings,selectedId,location) {
  const state=panels.get(panel); if (!state) return;
  if (state.holdings.map(x=>x.id).join(',')!==holdings.map(x=>x.id).join(',')) state.fit=true;
  if (state.location?.latitude!==location?.latitude || state.location?.longitude!==location?.longitude) state.fit=true;
  state.holdings=holdings; state.selectedId=selectedId; state.location=location;
  draw(panel,state);
}

function draw(panel,state) {
  if (!state.map) return;
  state.layer.clearLayers(); const points=[]; let selected;
  for (const holding of state.holdings) {
    if (!hasMapPoint(holding)) continue;
    const point=[holding.latitude,holding.longitude]; points.push(point);
    const marker=L.marker(point,{title:holding.name,icon:L.divIcon({className:`real-library-pin ${holding.status || 'unknown'}`,
      html:`<span>${icon(holding.status==='available'?'check':'book',18)}</span>`,iconSize:[36,40],iconAnchor:[18,35],popupAnchor:[0,-28]})});
    const homepage=webURL(holding.homepage);
    marker.bindPopup(`<section class="real-popup"><strong>${h(holding.name)}</strong>${holding.status?`<p>${h(statusText(holding))}</p>`:''}
      <p>${h(holding.neighborhood || '')}</p>${Number.isFinite(holding.distanceKm)?`<p>내 위치에서 ${distance(holding.distanceKm)} · 직선거리</p>`:''}
      ${homepage?`<a href="${homepage}" target="_blank" rel="noopener noreferrer">도서관 홈페이지 ↗</a>`:''}</section>`);
    marker.on('click',()=>panel.dispatchEvent(new CustomEvent('libraryselect',{bubbles:true,detail:{id:holding.id}})));
    marker.addTo(state.layer); if (holding.id===state.selectedId) selected=marker;
  }
  if (state.user) {state.user.remove();state.user=null;}
  if (hasMapPoint(state.location)) {
    const point=[state.location.latitude,state.location.longitude]; points.push(point);
    if (Number.isFinite(state.location.accuracy) && state.location.accuracy > 0) {
      L.circle(point,{radius:state.location.accuracy,color:'#2879ed',weight:1,fillColor:'#2879ed',fillOpacity:.07}).addTo(state.layer);
    }
    state.user=L.circleMarker(point,{radius:8,color:'white',weight:3,fillColor:'#2879ed',fillOpacity:1}).addTo(state.map)
      .bindTooltip('내 위치',{permanent:true,direction:'top',offset:[0,-12],className:'my-location-label'});
  }
  if (points.length && state.fit) {state.map.fitBounds(points,{padding:[60,90],maxZoom:14});state.fit=false;}
  if (selected) selected.openPopup();
}
