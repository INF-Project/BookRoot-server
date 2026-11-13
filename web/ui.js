const icons = {
  book: '<circle cx="12" cy="4.5" r="2.8"/><path d="M3 8.5c3.8.3 6.8 2 9 4.5 2.2-2.5 5.2-4.2 9-4.5v10c-3.8.2-6.8 1.6-9 4-2.2-2.4-5.2-3.8-9-4Z"/>',
  search: '<circle cx="10.5" cy="10.5" r="5.7"/><path d="m15 15 5 5"/>',
  pin: '<path d="M19 10c0 5-7 10-7 10S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2.2"/>',
  chevron: '<path d="m5 9 7 6 7-6"/>',
  navigation: '<path d="m21 3-7 17-3-7-7-3Z"/>',
  help: '<circle cx="12" cy="12" r="9.5"/><path d="M9.5 9a2.5 2.5 0 1 1 4.3 1.7c-1 .8-1.8 1.2-1.8 2.8M12 17h.01"/>',
  tree: '<path d="m12 2-4 6h2l-5 6h3l-3 4h14l-3-4h3l-5-6h2Zm0 16v4"/>',
  building: '<path d="M3 21V9h5V4h8v5h5v12ZM9 21v-4h6v4M6 12h.01M6 16h.01M18 12h.01M18 16h.01M11 8h.01M13 8h.01M11 12h.01M13 12h.01"/>',
  city: '<path d="M3 21V10h5v11m0-11V6l4-3v18m0-11h4v11m0-8h5v8ZM6 13h.01M6 17h.01M10 9h.01M10 14h.01M14 13h.01M14 17h.01M19 16h.01"/>',
  landmark: '<path d="m2 7 10-4 10 4ZM3 21h18M6 11v6m6-6v6m6-6v6"/>',
  network: '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="3" r="1.5"/><circle cx="21" cy="8" r="1.5"/><circle cx="18" cy="20" r="1.5"/><circle cx="6" cy="20" r="1.5"/><circle cx="3" cy="8" r="1.5"/><path d="M12 5v4m3 2 4.5-2m-5.5 5 3 4.5M10 14l-3 4.5M9 11 4.5 9"/>',
  park: '<path d="M4 21h17m-9 0v-7M4 11v10m3 0v-6H2m11-1h4a4 4 0 0 0 2-7 4 4 0 0 0-7-2 4.5 4.5 0 0 0 1 9Z"/><path d="M4 8h.01"/>',
  check: '<path d="m4.5 12 5 5 10-10"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l3 2"/>',
  cross: '<path d="m7 7 10 10m0-10L7 17"/>',
  bookmark: '<path d="M6 4h12v16l-6-4-6 4Z"/>',
  ruler: '<path d="M3 7h18v10H3Zm4 0v5m5-5v3m5-3v5"/>',
  phone: '<path d="m8 4 2 5-2 2a15 15 0 0 0 5 5l2-2 5 2v4C11 21 3 13 4 4Z"/>',
  layers: '<path d="m12 3 8 7-8 7-8-7Zm-8 12 8 7 8-7"/>',
  locate: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
  plus: '<path d="M6 12h12m-6-6v12"/>',
  minus: '<path d="M6 12h12"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/>',
};

// 반복해서 쓰는 아이콘에 장식 요소임을 표시합니다.
export function icon(name, size = 20) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
}

// 서버에서 받은 문자열을 HTML에 안전하게 표시합니다.
export function escapeHTML(value) {
  const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character]);
}

// 표지와 외부 링크는 HTTP 주소만 허용합니다.
export function webURL(value) {
  if (!value || typeof value !== 'string') return '';
  try {
    const url = new URL(value, document.baseURI);
    return ['http:', 'https:'].includes(url.protocol) ? escapeHTML(url.href) : '';
  } catch {
    return '';
  }
}

export const statusIcons = { available: 'checkCircle', borrowed: 'clock', unavailable: 'cross', unknown: 'help' };

export function statusText(holding) {
  switch (holding.status) {
    case 'available': return '정보나루: 대출 가능 · 전날';
    case 'borrowed': return '정보나루: 대출 중 · 전날';
    case 'unavailable': return '정보나루: 대출 불가 · 전날';
    default: return '상태 확인 불가';
  }
}

export function distance(km) {
  return Number.isFinite(km) && km >= 0 ? `${km.toFixed(1)}km` : '';
}
