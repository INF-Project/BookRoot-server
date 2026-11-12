"""WGS84 좌표 사이의 직선거리를 km 단위로 계산합니다."""

import math


def distance_km(latitude, longitude, target_latitude, target_longitude):
    if target_latitude is None or target_longitude is None:
        return None
    first, second = math.radians(latitude), math.radians(target_latitude)
    latitude_difference = second - first
    longitude_difference = math.radians(target_longitude - longitude)
    arc = (math.sin(latitude_difference / 2) ** 2
           + math.cos(first) * math.cos(second) * math.sin(longitude_difference / 2) ** 2)
    return round(6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, arc)))), 3)
