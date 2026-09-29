import random
import unittest

from mini_redis.hash_map import HashMap, fnv1a_hash
from mini_redis.linked_list import DoublyLinkedList
from mini_redis.min_heap import MinHeap


class DoublyLinkedListTest(unittest.TestCase):
    def test_insert_and_remove_both_ends(self):
        dll = DoublyLinkedList()
        dll.insert_back(2)
        dll.insert_front(1)
        dll.insert_back(3)
        self.assertEqual(list(dll), [1, 2, 3])
        self.assertEqual(dll.remove_front(), 1)
        self.assertEqual(dll.remove_back(), 3)
        self.assertEqual(list(dll), [2])
        self.assertEqual(dll.remove_back(), 2)
        self.assertIsNone(dll.remove_front())
        self.assertEqual(dll.size(), 0)

    def test_remove_node_and_move_to_front(self):
        dll = DoublyLinkedList()
        a = dll.insert_back("a")
        b = dll.insert_back("b")
        c = dll.insert_back("c")
        dll.move_to_front(c)
        self.assertEqual(list(dll), ["c", "a", "b"])
        dll.remove_node(a)
        self.assertEqual(list(dll), ["c", "b"])
        dll.move_to_front(b)
        self.assertEqual(list(dll), ["b", "c"])
        self.assertEqual(len(dll), 2)


class HashMapTest(unittest.TestCase):
    def test_basic_operations(self):
        m = HashMap()
        m.put("a", 1)
        m.put("b", 2)
        m.put("a", 3)
        self.assertEqual(m.get("a"), 3)
        self.assertTrue(m.contains("b"))
        self.assertEqual(m.size(), 2)
        self.assertTrue(m.remove("a"))
        self.assertFalse(m.remove("a"))
        self.assertIsNone(m.get("a"))
        self.assertEqual(m.keys(), ["b"])

    def test_resize_when_load_factor_exceeded(self):
        m = HashMap(capacity=4)
        for i in range(3):  # 3/4 = 0.75 → 아직 초과 아님
            m.put("k%d" % i, i)
        self.assertEqual(m.capacity(), 4)
        m.put("k3", 3)  # 4/4 > 0.75 → 2배 확장
        self.assertEqual(m.capacity(), 8)
        for i in range(4):
            self.assertEqual(m.get("k%d" % i), i)

    def test_collisions_are_chained(self):
        m = HashMap(capacity=1000)
        # 같은 버킷에 들어가는 키를 찾아 체이닝 동작을 확인
        target = fnv1a_hash("seed") % 1000
        colliding = [k for k in ("key%d" % i for i in range(20000))
                     if fnv1a_hash(k) % 1000 == target][:3]
        self.assertEqual(len(colliding), 3)
        for i, k in enumerate(colliding):
            m.put(k, i)
        for i, k in enumerate(colliding):
            self.assertEqual(m.get(k), i)
        m.remove(colliding[1])
        self.assertIsNone(m.get(colliding[1]))
        self.assertEqual(m.get(colliding[2]), 2)

    def test_many_keys(self):
        m = HashMap()
        for i in range(1000):
            m.put(str(i), i)
        self.assertEqual(m.size(), 1000)
        self.assertEqual(sorted(m.keys(), key=int), [str(i) for i in range(1000)])


class MinHeapTest(unittest.TestCase):
    def test_pops_in_sorted_order(self):
        h = MinHeap()
        values = [random.randint(0, 1000) for _ in range(200)]
        for v in values:
            h.push(v)
        self.assertEqual(h.peek(), min(values))
        self.assertEqual([h.pop() for _ in range(len(values))], sorted(values))
        self.assertIsNone(h.pop())
        self.assertIsNone(h.peek())

    def test_expire_tuples(self):
        h = MinHeap()
        h.push((30.0, "c"))
        h.push((10.0, "a"))
        h.push((20.0, "b"))
        self.assertEqual(h.size(), 3)
        self.assertEqual(h.pop(), (10.0, "a"))
        self.assertEqual(h.peek(), (20.0, "b"))


if __name__ == "__main__":
    unittest.main()
