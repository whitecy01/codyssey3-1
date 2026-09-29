import unittest

from mini_redis.cli import MiniRedis, tokenize
from mini_redis.store import RedisStore


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RedisTestBase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.redis = MiniRedis(RedisStore(clock=self.clock))

    def run_cmd(self, line):
        return self.redis.execute(line)


class StringCommandTest(RedisTestBase):
    def test_set_get(self):
        self.assertEqual(self.run_cmd('SET user:1 "Alice"'), "OK")
        self.assertEqual(self.run_cmd("GET user:1"), '"Alice"')
        self.assertEqual(self.run_cmd("GET nope"), "(nil)")

    def test_quoted_value_with_spaces(self):
        self.run_cmd('SET msg "hello world"')
        self.assertEqual(self.run_cmd("GET msg"), '"hello world"')

    def test_del_exists_dbsize_keys(self):
        self.assertEqual(self.run_cmd("KEYS"), "(empty array)")
        self.run_cmd("SET a 1")
        self.run_cmd("SET b 2")
        self.assertEqual(self.run_cmd("EXISTS a"), "(integer) 1")
        self.assertEqual(self.run_cmd("DBSIZE"), "(integer) 2")
        self.assertEqual(self.run_cmd("DEL a"), "(integer) 1")
        self.assertEqual(self.run_cmd("DEL a"), "(integer) 0")
        self.assertEqual(self.run_cmd("EXISTS a"), "(integer) 0")
        self.assertEqual(self.run_cmd("KEYS"), '1. "b"')
        self.assertEqual(self.redis.store.used_memory, 2)

    def test_case_insensitive_command(self):
        self.assertEqual(self.run_cmd("set k v"), "OK")
        self.assertEqual(self.run_cmd("get k"), '"v"')


class ErrorTest(RedisTestBase):
    def test_error_formats(self):
        self.assertEqual(self.run_cmd("CONFIG SET maxmemory abc"),
                         "(error) ERR value is not an integer or out of range")
        self.assertEqual(self.run_cmd("GET"),
                         "(error) ERR wrong number of arguments for 'GET' command")
        self.assertEqual(self.run_cmd("HELLO"),
                         "(error) ERR unknown command 'HELLO'")
        self.assertEqual(self.run_cmd("EXPIRE k x"),
                         "(error) ERR value is not an integer or out of range")

    def test_oom_single_entry_too_large(self):
        self.run_cmd("CONFIG SET maxmemory 5")
        self.assertEqual(self.run_cmd("SET key value"),
                         "(error) OOM command not allowed when used_memory > 'maxmemory'")
        self.assertEqual(self.run_cmd("EXISTS key"), "(integer) 0")
        self.assertEqual(self.redis.store.used_memory, 0)

    def test_empty_line(self):
        self.assertIsNone(self.run_cmd("   "))

    def test_unterminated_quote(self):
        self.assertTrue(self.run_cmd('SET a "oops').startswith("(error)"))


class LruTest(RedisTestBase):
    def test_example_scenario(self):
        """problem.md 결과 예시 재현."""
        self.assertEqual(self.run_cmd("CONFIG SET maxmemory 30"), "OK")
        self.assertEqual(self.run_cmd('SET user:1 "Alice"'), "OK")
        self.assertEqual(self.run_cmd('SET user:2 "Bob"'), "OK")
        self.assertEqual(self.run_cmd('SET user:3 "Charlie"'), "OK")
        self.assertEqual(self.run_cmd("GET user:1"), "(nil)")
        self.assertEqual(self.run_cmd("INFO memory"),
                         "# Memory\nused_memory:22\nmaxmemory:30\nevicted_keys:1")
        self.assertEqual(sorted(self.run_cmd("KEYS").split("\n")[i][3:] for i in range(2)),
                         ['"user:2"', '"user:3"'])
        self.assertEqual(self.run_cmd("EXPIRE user:2 3"), "(integer) 1")
        self.clock.now += 0.5
        self.assertEqual(self.run_cmd("TTL user:2"), "(integer) 2")
        self.clock.now += 3
        self.assertEqual(self.run_cmd("GET user:2"), "(nil)")
        self.assertEqual(self.run_cmd("TTL user:2"), "(integer) -2")
        self.assertEqual(self.redis.store.used_memory, 13)

    def test_get_refreshes_lru(self):
        self.run_cmd("CONFIG SET maxmemory 6")
        self.run_cmd("SET a 11")
        self.run_cmd("SET b 22")
        self.run_cmd("GET a")  # a가 최근 사용 → b가 LRU
        self.run_cmd("SET c 33")
        self.assertEqual(self.run_cmd("EXISTS a"), "(integer) 1")
        self.assertEqual(self.run_cmd("EXISTS b"), "(integer) 0")
        self.assertEqual(self.run_cmd("EXISTS c"), "(integer) 1")

    def test_overwrite_updates_memory_and_lru(self):
        self.run_cmd("CONFIG SET maxmemory 10")
        self.run_cmd("SET a 1")
        self.run_cmd("SET b 2")
        self.run_cmd("SET a 12345")  # a: 6바이트, b: 2바이트 → 8
        self.assertEqual(self.redis.store.used_memory, 8)
        self.run_cmd("SET c 123")  # 12 > 10 → LRU인 b 제거 → 10
        self.assertEqual(self.run_cmd("EXISTS b"), "(integer) 0")
        self.assertEqual(self.redis.store.used_memory, 10)
        self.assertEqual(self.redis.store.evicted_keys, 1)

    def test_lowering_maxmemory_evicts(self):
        self.run_cmd("SET a 1")
        self.run_cmd("SET b 2")
        self.run_cmd("CONFIG SET maxmemory 2")
        self.assertEqual(self.run_cmd("KEYS"), '1. "b"')

    def test_utf8_byte_length(self):
        self.run_cmd('SET 이름 "홍길동"')
        self.assertEqual(self.redis.store.used_memory, 6 + 9)


class TtlTest(RedisTestBase):
    def test_ttl_states(self):
        self.assertEqual(self.run_cmd("TTL k"), "(integer) -2")
        self.run_cmd("SET k v")
        self.assertEqual(self.run_cmd("TTL k"), "(integer) -1")
        self.assertEqual(self.run_cmd("EXPIRE k 10"), "(integer) 1")
        self.assertEqual(self.run_cmd("TTL k"), "(integer) 10")

    def test_expire_missing_key(self):
        self.assertEqual(self.run_cmd("EXPIRE nope 10"), "(integer) 0")

    def test_expire_non_positive_deletes(self):
        self.run_cmd("SET k v")
        self.assertEqual(self.run_cmd("EXPIRE k 0"), "(integer) 1")
        self.assertEqual(self.run_cmd("EXISTS k"), "(integer) 0")
        self.assertEqual(self.redis.store.used_memory, 0)

    def test_set_resets_ttl(self):
        self.run_cmd("SET k v")
        self.run_cmd("EXPIRE k 5")
        self.run_cmd("SET k v2")
        self.assertEqual(self.run_cmd("TTL k"), "(integer) -1")
        self.clock.now += 10  # 옛 힙 항목이 남아 있어도 삭제되면 안 된다
        self.assertEqual(self.run_cmd("GET k"), '"v2"')

    def test_re_expire_uses_latest(self):
        self.run_cmd("SET k v")
        self.run_cmd("EXPIRE k 5")
        self.run_cmd("EXPIRE k 20")
        self.clock.now += 10
        self.assertEqual(self.run_cmd("EXISTS k"), "(integer) 1")
        self.clock.now += 11
        self.assertEqual(self.run_cmd("EXISTS k"), "(integer) 0")

    def test_active_expire_via_heap(self):
        for i in range(5):
            self.run_cmd("SET k%d v" % i)
            self.run_cmd("EXPIRE k%d %d" % (i, i + 1))
        self.clock.now += 3
        self.assertEqual(self.run_cmd("DBSIZE"), "(integer) 2")
        self.assertEqual(self.redis.store.used_memory, 6)

    def test_del_removes_ttl(self):
        self.run_cmd("SET k v")
        self.run_cmd("EXPIRE k 5")
        self.run_cmd("DEL k")
        self.run_cmd("SET k v")
        self.clock.now += 10
        self.assertEqual(self.run_cmd("GET k"), '"v"')


class TokenizeTest(unittest.TestCase):
    def test_tokenize(self):
        self.assertEqual(tokenize('SET a "b c"'), ["SET", "a", "b c"])
        self.assertEqual(tokenize('SET a "say \\"hi\\""'), ["SET", "a", 'say "hi"'])
        self.assertEqual(tokenize("  GET   x  "), ["GET", "x"])


if __name__ == "__main__":
    unittest.main()
