"""이중 연결 리스트 (Doubly Linked List).

head/tail 센티널(sentinel) 노드를 두어 경계 조건 분기 없이
모든 삽입/삭제/이동 연산을 O(1)로 수행한다.

사용처
- 해시맵 버킷의 체이닝 저장소
- LRU 추적 리스트 (front = 가장 최근 사용, back = 가장 오래 전 사용)
"""


class Node:
    """리스트 노드. prev/next 포인터와 data 필드를 가진다."""

    __slots__ = ("prev", "next", "data")

    def __init__(self, data=None):
        self.prev = None
        self.next = None
        self.data = data


class DoublyLinkedList:
    """센티널 기반 이중 연결 리스트."""

    def __init__(self):
        self._head = Node()  # 센티널: 실제 첫 노드는 _head.next
        self._tail = Node()  # 센티널: 실제 마지막 노드는 _tail.prev
        self._head.next = self._tail
        self._tail.prev = self._head
        self._size = 0

    # ---------- 내부 헬퍼 ----------

    def _link_after(self, anchor, node):
        """anchor 바로 뒤에 node를 연결한다. O(1)"""
        node.prev = anchor
        node.next = anchor.next
        anchor.next.prev = node
        anchor.next = node
        self._size += 1

    def _unlink(self, node):
        """node를 리스트에서 떼어낸다. O(1)"""
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = None
        node.next = None
        self._size -= 1

    # ---------- 공개 API ----------

    def insert_front(self, data):
        """맨 앞에 data를 삽입하고 생성된 노드를 반환한다. O(1)"""
        node = Node(data)
        self._link_after(self._head, node)
        return node

    def insert_back(self, data):
        """맨 뒤에 data를 삽입하고 생성된 노드를 반환한다. O(1)"""
        node = Node(data)
        self._link_after(self._tail.prev, node)
        return node

    def remove_front(self):
        """맨 앞 노드를 제거하고 그 data를 반환한다. 비어 있으면 None. O(1)"""
        if self._size == 0:
            return None
        node = self._head.next
        self._unlink(node)
        return node.data

    def remove_back(self):
        """맨 뒤 노드를 제거하고 그 data를 반환한다. 비어 있으면 None. O(1)"""
        if self._size == 0:
            return None
        node = self._tail.prev
        self._unlink(node)
        return node.data

    def remove_node(self, node):
        """주어진 노드를 제거하고 그 data를 반환한다. O(1)

        노드 참조를 이미 가지고 있으므로 탐색 없이 바로 끊어낼 수 있다.
        """
        self._unlink(node)
        return node.data

    def move_to_front(self, node):
        """주어진 노드를 맨 앞으로 옮긴다. O(1)"""
        if self._head.next is node:
            return
        self._unlink(node)
        self._link_after(self._head, node)

    def peek_back(self):
        """맨 뒤 노드의 data를 제거하지 않고 반환한다. 비어 있으면 None."""
        if self._size == 0:
            return None
        return self._tail.prev.data

    def nodes(self):
        """앞에서부터 노드를 순회하는 제너레이터."""
        cur = self._head.next
        while cur is not self._tail:
            nxt = cur.next  # 순회 중 삭제에 대비해 미리 저장
            yield cur
            cur = nxt

    def __iter__(self):
        for node in self.nodes():
            yield node.data

    def __len__(self):
        return self._size

    def size(self):
        return self._size
