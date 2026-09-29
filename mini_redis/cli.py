"""Mini Redis CLI: 입력 파싱 → 명령 실행 → Redis 스타일 출력."""

from .store import RedisError, RedisStore

PROMPT = "mini-redis> "


class ParseError(Exception):
    pass


def tokenize(line):
    """공백으로 인자를 나누되, 큰따옴표로 감싼 부분은 하나의 인자로 취급한다.

    예) SET greeting "hello world"  →  ['SET', 'greeting', 'hello world']
    따옴표 안에서는 \\" 와 \\\\ 이스케이프를 지원한다.
    """
    tokens = []
    i, n = 0, len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        if line[i] == '"':
            i += 1
            chars = []
            while i < n and line[i] != '"':
                if line[i] == "\\" and i + 1 < n:
                    i += 1
                chars.append(line[i])
                i += 1
            if i >= n:
                raise ParseError("Invalid argument(s)")
            i += 1  # 닫는 따옴표
            if i < n and not line[i].isspace():
                raise ParseError("Invalid argument(s)")
            tokens.append("".join(chars))
        else:
            start = i
            while i < n and not line[i].isspace():
                i += 1
            tokens.append(line[start:i])
    return tokens


# ---------- 출력 포맷 ----------

def quote(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt_integer(n):
    return "(integer) %d" % n


def fmt_bulk(value):
    return "(nil)" if value is None else quote(value)


def fmt_array(items):
    if not items:
        return "(empty array)"
    return "\n".join("%d. %s" % (i + 1, quote(item)) for i, item in enumerate(items))


# ---------- 명령 실행 ----------

def parse_int(text):
    try:
        return int(text)
    except ValueError:
        raise RedisError("ERR value is not an integer or out of range")


def wrong_args(name):
    return RedisError("ERR wrong number of arguments for '%s' command" % name)


class MiniRedis:
    """명령 한 줄을 받아 결과 문자열을 돌려주는 디스패처."""

    def __init__(self, store=None):
        self.store = store or RedisStore()
        # 명령 이름 → (핸들러, 인자 개수 검사 함수)
        # 명령 테이블이라 튜플 목록으로 두고 선형 탐색한다 (dict 사용 금지).
        self._commands = [
            ("SET", self._set, lambda n: n == 2),
            ("GET", self._get, lambda n: n == 1),
            ("DEL", self._del, lambda n: n >= 1),
            ("EXISTS", self._exists, lambda n: n >= 1),
            ("DBSIZE", self._dbsize, lambda n: n == 0),
            ("KEYS", self._keys, lambda n: n <= 1),
            ("CONFIG", self._config, lambda n: n >= 1),
            ("INFO", self._info, lambda n: n <= 1),
            ("EXPIRE", self._expire, lambda n: n == 2),
            ("TTL", self._ttl, lambda n: n == 1),
        ]

    def execute(self, line):
        """한 줄을 실행하고 출력할 문자열을 반환한다. 빈 줄이면 None."""
        try:
            tokens = tokenize(line)
        except ParseError as e:
            return "(error) ERR %s" % e
        if not tokens:
            return None

        name, args = tokens[0], tokens[1:]
        for cmd, handler, arity_ok in self._commands:
            if cmd == name.upper():
                break
        else:
            return "(error) ERR unknown command '%s'" % name

        try:
            if not arity_ok(len(args)):
                raise wrong_args(name)
            # 명령 실행 전 힙 루트에서 만료된 키를 정리한다 (active expire)
            self.store.purge_expired()
            return handler(name, args)
        except RedisError as e:
            return "(error) %s" % e

    # 각 핸들러는 (입력한 명령 이름, 인자 목록)을 받는다.

    def _set(self, name, args):
        return self.store.set(args[0], args[1])

    def _get(self, name, args):
        return fmt_bulk(self.store.get(args[0]))

    def _del(self, name, args):
        return fmt_integer(sum(self.store.delete(k) for k in args))

    def _exists(self, name, args):
        return fmt_integer(sum(self.store.exists(k) for k in args))

    def _dbsize(self, name, args):
        return fmt_integer(self.store.dbsize())

    def _keys(self, name, args):
        # 패턴 매칭은 지원하지 않으므로 인자가 있다면 '*'만 허용한다
        if args and args[0] != "*":
            raise RedisError("ERR pattern matching is not supported (use KEYS or KEYS *)")
        return fmt_array(self.store.keys())

    def _config(self, name, args):
        sub = args[0].upper()
        if sub == "SET":
            if len(args) != 3:
                raise wrong_args("config|set")
            if args[1].lower() != "maxmemory":
                raise RedisError("ERR Unsupported CONFIG parameter: %s" % args[1])
            value = parse_int(args[2])
            if value < 0:
                raise RedisError("ERR value is not an integer or out of range")
            return self.store.config_set_maxmemory(value)
        if sub == "GET":
            if len(args) != 2:
                raise wrong_args("config|get")
            if args[1].lower() != "maxmemory":
                return "(empty array)"
            return "1. \"maxmemory\"\n2. \"%d\"" % self.store.maxmemory
        raise RedisError("ERR unknown subcommand '%s'" % args[0])

    def _info(self, name, args):
        if args and args[0].lower() != "memory":
            raise RedisError("ERR unsupported INFO section '%s'" % args[0])
        lines = ["# Memory"]
        for field, value in self.store.info_memory():
            lines.append("%s:%d" % (field, value))
        return "\n".join(lines)

    def _expire(self, name, args):
        seconds = parse_int(args[1])
        return fmt_integer(self.store.expire(args[0], seconds))

    def _ttl(self, name, args):
        return fmt_integer(self.store.ttl(args[0]))


def repl():
    """mini-redis> 프롬프트로 입력을 반복 처리한다. exit/quit 또는 EOF로 종료."""
    redis = MiniRedis()
    while True:
        try:
            line = input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip().lower() in ("exit", "quit"):
            break
        output = redis.execute(line)
        if output is not None:
            print(output)
