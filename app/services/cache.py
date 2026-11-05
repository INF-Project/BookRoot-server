from collections import OrderedDict
from time import monotonic


class TTLCache:
    """외부 응답 및 검색 이어보기 상태를 잠깐 보관하는 크기 제한 캐시입니다."""

    def __init__(self, max_size=256, ttl=300, clock=monotonic):
        self.max_size = max_size
        self.ttl = ttl
        self.clock = clock
        self._entries = OrderedDict()

    def get(self, key):
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= self.clock():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def put(self, key, value):
        self._entries[key] = (self.clock() + self.ttl, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_size:
            self._entries.popitem(last=False)
