// 실서버 연결 시 '/api' 또는 서버 API의 기본 URL을 입력합니다.
export const API_BASE_URL = '/api';
// 현재 로컬 DB에 검증·적재한 공식 공개 파일의 기준월입니다.
export const CATALOG_SNAPSHOT_LABEL = '2026년 10월';

// 대전 예시 지도의 위·경도 범위입니다.
export const SAMPLE_MAP_BOUNDS = Object.freeze({
  west: 127.275,
  east: 127.435,
  north: 36.426,
  south: 36.284,
});

export const SAMPLE_USER_LOCATION = Object.freeze({
  latitude: 36.34542,
  longitude: 127.34547,
  label: '유성구 온천2동',
  districtId: 'yuseong',
});
