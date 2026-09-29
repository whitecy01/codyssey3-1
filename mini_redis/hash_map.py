"""체이닝 방식 해시맵 (Hash Map with Separate Chaining).

- 해시 함수: FNV-1a 32bit를 직접 구현 (문자열을 UTF-8 바이트로 변환 후 계산)
- 충돌 해결: 각 버킷이 이중 연결 리스트(DoublyLinkedList)를 체인으로 가진다
- 리사이즈: 로드 팩터(size / capacity)가 0.75를 넘으면 버킷 수를 2배로 늘리고 재해싱

버킷 테이블은 "고정 길이 배열 + 인덱스 접근" 용도로만 파이썬 list를 사용한다.
"""

from .linked_list import DoublyLinkedList

FNV_OFFSET_BASIS = 0x811C9DC5
FNV_PRIME = 0x01000193
MASK_32 = 0xFFFFFFFF


def fnv1a_hash(key):
    """FNV-1a 32bit 해시.

    각 바이트마다 (hash XOR byte) * FNV_PRIME 을 반복한다.
    XOR 후 곱셈을 하므로 입력의 작은 차이도 상위 비트까지 잘 퍼진다.
    """
    h = FNV_OFFSET_BASIS
    for byte in str(key).encode("utf-8"):
        h ^= byte
        h = (h * FNV_PRIME) & MASK_32
    return h


class _Entry:
    """체인에 저장되는 (key, value) 쌍. value 갱신을 위해 가변 객체로 둔다."""

    __slots__ = ("key", "value")

    def __init__(self, key, value):
        self.key = key
        self.value = value


class HashMap:
    """체이닝 해시맵."""

    LOAD_FACTOR = 0.75

    def __init__(self, capacity=8):
        self._capacity = capacity
        self._buckets = [None] * capacity  # 버킷은 필요할 때 생성(lazy)
        self._size = 0

    # ---------- 내부 헬퍼 ----------

    def _index(self, key):
        """키 → 버킷 인덱스."""
        return fnv1a_hash(key) % self._capacity

    def _find_node(self, key):
        """키에 해당하는 체인 노드를 찾는다. (bucket, node) 또는 (bucket, None)."""
        bucket = self._buckets[self._index(key)]
        if bucket is None:
            return None, None
        for node in bucket.nodes():
            if node.data.key == key:
                return bucket, node
        return bucket, None

    def _resize(self, new_capacity):
        """버킷 수를 new_capacity로 바꾸고 모든 엔트리를 재해싱한다."""
        old_buckets = self._buckets
        self._capacity = new_capacity
        self._buckets = [None] * new_capacity
        for bucket in old_buckets:
            if bucket is None:
                continue
            for entry in bucket:
                idx = self._index(entry.key)
                if self._buckets[idx] is None:
                    self._buckets[idx] = DoublyLinkedList()
                self._buckets[idx].insert_back(entry)

    # ---------- 공개 API ----------

    def put(self, key, value):
        """key에 value를 저장한다. 이미 있으면 덮어쓴다. 평균 O(1)"""
        _, node = self._find_node(key)
        if node is not None:
            node.data.value = value
            return

        idx = self._index(key)
        if self._buckets[idx] is None:
            self._buckets[idx] = DoublyLinkedList()
        self._buckets[idx].insert_back(_Entry(key, value))
        self._size += 1

        if self._size / self._capacity > self.LOAD_FACTOR:
            self._resize(self._capacity * 2)

    def get(self, key, default=None):
        """key의 값을 반환한다. 없으면 default. 평균 O(1)"""
        _, node = self._find_node(key)
        return default if node is None else node.data.value

    def remove(self, key):
        """key를 삭제한다. 삭제했으면 True, 없었으면 False. 평균 O(1)"""
        bucket, node = self._find_node(key)
        if node is None:
            return False
        bucket.remove_node(node)
        self._size -= 1
        return True

    def contains(self, key):
        """key 존재 여부. 평균 O(1)"""
        return self._find_node(key)[1] is not None

    def keys(self):
        """전체 키 목록. O(n + capacity)"""
        result = []
        for bucket in self._buckets:
            if bucket is None:
                continue
            for entry in bucket:
                result.append(entry.key)
        return result

    def size(self):
        return self._size

    def capacity(self):
        return self._capacity

    def __len__(self):
        return self._size

    def __contains__(self, key):
        return self.contains(key)
