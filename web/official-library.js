import { webURL } from './ui.js';

// 2026-11-12 공식 상세검색의 소장처 선택지와 정보나루 도서관명을 대조했습니다.
// 정보나루 코드와 공식 검색의 소장처 코드는 서로 다릅니다.
const libraryFilters = {
  '125010':'H0000014', '125008':'H0000003', '125004':'H0000011',
  '130023':'H0000030', '130022':'H0000020', '125013':'H0000019',
  '130012':'H0000015', '130007':'H0000017', '125002':'H0000024',
  '130006':'H0000012', '143064':'H0000008', '125001':'H0000025',
  '130030':'H0000029', '130013':'H0000023', '125005':'H0000022',
  '125006':'H0000004', '130026':'H0000026', '130028':'H0000027',
  '125007':'H0000016', '12500701':'H0000013', '130008':'H0000010',
  '130031':'H0000031', '130010':'H0000018', '130004':'H0000006',
  '125003':'H0000001', '130009':'H0000009',
};

export function officialBookLink(isbn13, bookTitle, holding) {
  if (typeof isbn13 !== 'string' || !/^[0-9]{13}$/.test(isbn13)) return null;
  const filter = libraryFilters[holding.id];
  if (!filter) {
    const href = webURL(holding.homepage);
    return href ? {href,kind:'homepage'} : null;
  }
  // 공식 '전체' 검색은 ISBN 검색을 지원하지 않습니다. 제목으로 찾고 ISBN을 대조합니다.
  const title = typeof bookTitle === 'string' ? bookTitle.split(/[:：=]/u)[0].trim() : '';
  const url = new URL('https://www.u-library.kr/search/tot');
  if (!title) return {href:webURL(url.href),kind:'manual'};
  url.pathname += '/result';
  // bk_8은 실제 소장처 필터 링크에서 확인한 조건입니다. lmt0만으로는 제한되지 않습니다.
  url.search = new URLSearchParams({st:'KWRD',si:'1',q:title,lmt0:filter,bk_8:filter});
  return {href:webURL(url.href),kind:'filtered'};
}
