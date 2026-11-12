import math

def distance_km(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    """WGS84 좌표 사이 직선거리(km), 길찾기 거리가 아닙니다."""
    lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(other_longitude-longitude)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(max(0, min(1, a))))
