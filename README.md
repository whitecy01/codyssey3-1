# Mini Redis

해시맵, 이중 연결 리스트, 최소 힙을 직접 구현해서 만든 CLI 기반 Key-Value 저장소입니다.
`dict`, `set`, `collections`는 쓰지 않았습니다.

## 실행

```bash
python3 main.py                                  # REPL (exit / quit 로 종료)
python3 -m unittest discover -s tests -t .       # 테스트
```

## 구조

| 파일 | 역할 |
| --- | --- |
| `mini_redis/linked_list.py` | 이중 연결 리스트 (`insert_front/back`, `remove_front/back`, `remove_node`, `move_to_front`) |
| `mini_redis/hash_map.py` | 체이닝 해시맵 (FNV-1a 해시, 로드 팩터 0.75 초과 시 2배 확장) |
| `mini_redis/min_heap.py` | 최소 힙 (`push`, `pop`, `peek`, `_heapify_up/down`) |
| `mini_redis/store.py` | 세 자료구조를 조합한 저장소 (LRU 제거, TTL 만료, used_memory) |
| `mini_redis/cli.py` | 입력 파싱, 명령 실행, Redis 스타일 출력, REPL |

## 지원 명령

`SET` `GET` `DEL` `EXISTS` `DBSIZE` `KEYS` `CONFIG SET maxmemory <bytes>` `INFO memory` `EXPIRE` `TTL`
(부가 기능: `CONFIG GET maxmemory`, 여러 키를 받는 `DEL`/`EXISTS`)

## 핵심 설계

**해시맵과 체이닝.** 키를 UTF-8 바이트로 바꾼 뒤 FNV-1a로 해시하고, `hash % capacity`로 버킷을 고릅니다.
버킷 하나가 이중 연결 리스트여서 같은 버킷에 들어간 키들은 그 리스트에 이어 붙습니다.
`size / capacity > 0.75`가 되면 버킷 수를 2배로 늘리고 모든 키를 다시 해싱합니다.

**O(1) LRU.** 해시맵 값(`Record`)에 LRU 리스트 노드 참조를 넣어 둡니다.
키로 노드를 O(1)에 찾고, 이중 연결 리스트라서 노드를 떼어 맨 앞으로 옮기는 것도 O(1)입니다.
리스트 앞쪽은 최근에 쓴 키, 뒤쪽은 가장 오래전에 쓴 키입니다.

**힙으로 TTL 관리.** `(expire_at, key)`를 최소 힙에 넣으면 가장 먼저 만료될 키가 항상 루트에 옵니다.
명령을 실행하기 전에 루트의 만료 시각이 지났는지 보고, 지났으면 꺼내서 삭제합니다(active expire).
루트가 아직 만료 전이면 나머지도 모두 만료 전이므로 바로 멈춥니다.
그와 별개로 키를 조회할 때도 만료 여부를 확인합니다(passive expire).
EXPIRE를 다시 걸거나 SET으로 TTL이 초기화되면 힙에 있던 옛 항목은 그대로 둡니다.
나중에 꺼낼 때 `Record.expire_at`과 값이 다르면 버립니다(lazy deletion).

**메모리 제한 흐름 (SET).**
1. `len(utf8(key)) + len(utf8(value))`가 `maxmemory`보다 크면 저장하지 않고 OOM 에러를 반환합니다.
2. 저장하면서 `used_memory`에 크기를 더합니다. 덮어쓰는 경우에는 이전 값과의 차이만 반영합니다. 노드는 LRU 맨 앞에 둡니다.
3. `used_memory > maxmemory`인 동안 LRU 리스트의 맨 뒤 키를 삭제합니다. 삭제할 때마다 `used_memory`를 줄이고 `evicted_keys`를 1 올립니다.
