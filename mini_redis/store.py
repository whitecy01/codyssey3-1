"""Mini Redis 저장소 엔진.

세 자료구조를 조합한다.

    HashMap[key] ──► Record(value, lru_node, expire_at)
                          │
                          ▼
    LRU 리스트:  front(최근 사용) ◄──► ... ◄──► back(가장 오래 전 사용)

    TTL 힙:      (expire_at, key) 최소 힙 → 가장 빨리 만료될 키가 루트

- 해시맵이 lru_node 참조를 들고 있으므로 "키 → 리스트 노드"를 O(1)에 찾고,
  이중 연결 리스트의 move_to_front / remove_node 로 LRU 갱신도 O(1)이다.
- TTL 힙은 lazy deletion을 쓴다. EXPIRE를 다시 걸거나 SET으로 TTL이
  초기화돼도 힙의 옛 항목은 그대로 두고, 꺼낼 때 Record.expire_at과
  일치하는지 확인해 다르면 버린다.
"""

import time

from .hash_map import HashMap
from .linked_list import DoublyLinkedList
from .min_heap import MinHeap


class RedisError(Exception):
    """Redis 스타일 에러. 메시지는 '(error) ' 뒤에 붙는 부분이다."""


OOM_MESSAGE = "OOM command not allowed when used_memory > 'maxmemory'"


class Record:
    """키 하나에 대한 저장 정보."""

    __slots__ = ("value", "lru_node", "expire_at")

    def __init__(self, value, lru_node, expire_at=None):
        self.value = value
        self.lru_node = lru_node
        self.expire_at = expire_at


def entry_size(key, value):
    """used_memory 산정 공식: len(utf8(key)) + len(utf8(value))."""
    return len(key.encode("utf-8")) + len(value.encode("utf-8"))


class RedisStore:
    """String 타입 + LRU 제거 + TTL 만료를 지원하는 인메모리 저장소."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock  # 테스트에서 가짜 시계를 주입할 수 있다
        self._data = HashMap()
        self._lru = DoublyLinkedList()
        self._ttl_heap = MinHeap()
        self.used_memory = 0
        self.maxmemory = 0  # 0 = 무제한
        self.evicted_keys = 0

    # ---------- 내부: 삭제 / 만료 / LRU ----------

    def _delete(self, key):
        """데이터·LRU·메모리 사용량에서 키를 제거한다.

        TTL 힙의 항목은 lazy deletion으로 나중에 버려진다.
        """
        record = self._data.get(key)
        if record is None:
            return False
        self._lru.remove_node(record.lru_node)
        self._data.remove(key)
        self.used_memory -= entry_size(key, record.value)
        return True

    def _is_expired(self, record):
        return record.expire_at is not None and record.expire_at <= self._clock()

    def _lookup(self, key):
        """키를 조회하되, 만료됐다면 삭제하고 None을 반환한다 (passive expire)."""
        record = self._data.get(key)
        if record is None:
            return None
        if self._is_expired(record):
            self._delete(key)
            return None
        return record

    def purge_expired(self):
        """힙 루트부터 만료된 키를 꺼내 삭제한다 (active expire).

        루트가 아직 만료 전이면 나머지도 모두 만료 전이므로 바로 멈춘다.
        """
        now = self._clock()
        while self._ttl_heap.size() > 0:
            expire_at, key = self._ttl_heap.peek()
            if expire_at > now:
                break
            self._ttl_heap.pop()
            record = self._data.get(key)
            # 현재 레코드의 만료 시각과 같을 때만 유효한 항목 (lazy deletion)
            if record is not None and record.expire_at == expire_at:
                self._delete(key)

    def _evict_until_fit(self):
        """used_memory가 maxmemory 이하가 될 때까지 LRU(리스트 back)부터 제거한다."""
        if self.maxmemory <= 0:
            return
        while self.used_memory > self.maxmemory and self._lru.size() > 0:
            victim = self._lru.peek_back()
            self._delete(victim)
            self.evicted_keys += 1

    # ---------- String 명령 ----------

    def set(self, key, value):
        """SET key value. 덮어쓰면 TTL은 초기화된다."""
        size = entry_size(key, value)
        if self.maxmemory > 0 and size > self.maxmemory:
            raise RedisError(OOM_MESSAGE)

        record = self._lookup(key)
        if record is not None:
            self.used_memory += size - entry_size(key, record.value)
            record.value = value
            record.expire_at = None  # TTL 초기화 (힙 항목은 lazy deletion)
            self._lru.move_to_front(record.lru_node)
        else:
            node = self._lru.insert_front(key)
            self._data.put(key, Record(value, node))
            self.used_memory += size

        self._evict_until_fit()
        return "OK"

    def get(self, key):
        """GET key. 성공한 경우에만 LRU를 갱신한다."""
        record = self._lookup(key)
        if record is None:
            return None
        self._lru.move_to_front(record.lru_node)
        return record.value

    def delete(self, key):
        """DEL key. 삭제했으면 1, 없으면 0."""
        return 1 if self._lookup(key) is not None and self._delete(key) else 0

    def exists(self, key):
        """EXISTS key. 있으면 1, 없으면 0."""
        return 1 if self._lookup(key) is not None else 0

    def dbsize(self):
        self.purge_expired()
        return self._data.size()

    def keys(self):
        self.purge_expired()
        return self._data.keys()

    # ---------- TTL 명령 ----------

    def expire(self, key, seconds):
        """EXPIRE key seconds. 없으면 0, 설정(또는 즉시 만료)하면 1."""
        record = self._lookup(key)
        if record is None:
            return 0
        if seconds <= 0:
            self._delete(key)
            return 1
        record.expire_at = self._clock() + seconds
        self._ttl_heap.push((record.expire_at, key))
        return 1

    def ttl(self, key):
        """TTL key. 없으면 -2, 만료 없음 -1, 그 외 남은 초."""
        record = self._lookup(key)
        if record is None:
            return -2
        if record.expire_at is None:
            return -1
        return int(record.expire_at - self._clock())

    # ---------- 메모리 명령 ----------

    def config_set_maxmemory(self, maxmemory):
        """CONFIG SET maxmemory. 줄어든 한도에 맞춰 즉시 LRU 제거를 수행한다."""
        self.maxmemory = maxmemory
        self._evict_until_fit()
        return "OK"

    def info_memory(self):
        return [
            ("used_memory", self.used_memory),
            ("maxmemory", self.maxmemory),
            ("evicted_keys", self.evicted_keys),
        ]
