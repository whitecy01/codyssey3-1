"""최소 힙 (Min Heap).

완전 이진 트리를 배열로 표현한다.
- 부모: (i - 1) // 2
- 왼쪽 자식: 2i + 1, 오른쪽 자식: 2i + 2

TTL 관리에서는 (expire_at, key) 튜플을 넣어 가장 빨리 만료되는 키를
peek으로 O(1)에 확인하고, pop으로 O(log n)에 꺼낸다.
"""


class MinHeap:
    """배열 기반 최소 힙. 요소는 서로 < 비교가 가능해야 한다."""

    def __init__(self):
        self._items = []

    def push(self, item):
        """요소를 추가한다. O(log n)"""
        self._items.append(item)
        self._heapify_up(len(self._items) - 1)

    def pop(self):
        """최솟값을 꺼내 반환한다. 비어 있으면 None. O(log n)"""
        if not self._items:
            return None
        last = self._items.pop()
        if not self._items:
            return last
        top = self._items[0]
        self._items[0] = last
        self._heapify_down(0)
        return top

    def peek(self):
        """최솟값을 제거하지 않고 반환한다. 비어 있으면 None. O(1)"""
        return self._items[0] if self._items else None

    def size(self):
        return len(self._items)

    def __len__(self):
        return len(self._items)

    def _heapify_up(self, i):
        """i 위치 요소를 부모보다 작으면 위로 올린다."""
        items = self._items
        while i > 0:
            parent = (i - 1) // 2
            if items[i] < items[parent]:
                items[i], items[parent] = items[parent], items[i]
                i = parent
            else:
                break

    def _heapify_down(self, i):
        """i 위치 요소를 더 작은 자식과 비교해 아래로 내린다."""
        items = self._items
        n = len(items)
        while True:
            left = 2 * i + 1
            right = left + 1
            smallest = i
            if left < n and items[left] < items[smallest]:
                smallest = left
            if right < n and items[right] < items[smallest]:
                smallest = right
            if smallest == i:
                break
            items[i], items[smallest] = items[smallest], items[i]
            i = smallest
