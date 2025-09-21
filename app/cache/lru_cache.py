import asyncio
from collections import OrderedDict


class LRUCache:

    def __init__(self, capacity: int):
        self._capacity = capacity
        self._data: OrderedDict[str, bytes] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> bytes | None:
        async with self._lock:
            value = self._data.get(key)

            if value is not None:
                self._data.move_to_end(key)

            return value

    async def set(self, key: str, value: bytes) -> None:
        async with self._lock:
            if key in self._data:
                self._data.move_to_end(key)

            self._data[key] = value

            while len(self._data) > self._capacity:
                self._data.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
