from __future__ import annotations
import asyncio
import contextlib
import gzip
import os
from pathlib import Path
import shutil
from types import TracebackType
import tempfile
from typing import AsyncContextManager, ContextManager
import logging

logger = logging.getLogger(__name__)


class _ExclusiveFileLock(ContextManager):

    def __init__(self, path: Path):
        self._path = path
        self._is_acquired = False

    def is_acquired(self) -> bool:
        return self._is_acquired

    def __enter__(self) -> _ExclusiveFileLock:
        path = self._path
        is_acquired = False

        try:
            fd = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
            os.close(fd)
            is_acquired = True
        except FileExistsError:
            pass

        self._is_acquired = is_acquired
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._is_acquired:
            with contextlib.suppress(Exception):
                self._path.unlink(missing_ok=True)


class _ExclusiveFileAccess(ContextManager):

    def __init__(self, disk_cache: DiskCache, path: Path):
        self._disk_cache = disk_cache
        self._path = path
        self._data: bytes | None = None

    def __enter__(self) -> _ExclusiveFileAccess:
        disk_cache = self._disk_cache
        path = self._path
        data = disk_cache._read_disk(path)
        self._data = data

        if data is not None:
            return self

        lock_path = disk_cache._lock_path(path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with _ExclusiveFileLock(lock_path) as lock:
            if not lock.is_acquired():
                return self

            data = disk_cache._read_disk(path)
            self._data = data

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if (data := self._data) is not None:
            self._disk_cache._write_disk(self._path, data)
            self._disk_cache._enforce_disk_size_limit()

    def set_data(self, data: bytes) -> None:
        self._data = data

    def get_data(self) -> bytes | None:
        return self._data


class _CoalescedAccessState:

    def __init__(self, max_concurrency: int):
        self._inflight: dict[str, asyncio.Future[bytes | None]] = {}
        self._inflight_lock = asyncio.Lock()
        self._write_semaphore = asyncio.Semaphore(max_concurrency)

    async def get_future(self, key: str) -> asyncio.Future[bytes | None]:
        async with self._inflight_lock:
            if (fut := self._inflight.get(key)) is None:
                fut = asyncio.get_running_loop().create_future()
                self._inflight[key] = fut

        return fut

    async def delete_future(self, key: str) -> None:
        async with self._inflight_lock:
            self._inflight.pop(key, None)

    async def acquire_write_barrier(self) -> None:
        await self._write_semaphore.__aenter__()

    async def release_write_barrier(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._write_semaphore.__aexit__(exc_type, exc_value, traceback)

    async def clear(self) -> None:
        async with self._inflight_lock:
            self._inflight.clear()


class _CoalescedAccess(AsyncContextManager):

    def __init__(self, disk_cache: DiskCache, key: str):
        self._disk_cache = disk_cache
        self._key = key
        self._fut: asyncio.Future[bytes | None] | None = None
        self._is_acquired = False

    async def __aenter__(self) -> _CoalescedAccess:
        state = self._disk_cache._state
        key = self._key

        fut = await state.get_future(key)
        self._fut = fut

        if not fut.done():
            await state.acquire_write_barrier()
            is_acquired = not fut.done()
            self._is_acquired = is_acquired

            if not is_acquired:
                await state.release_write_barrier()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._is_acquired:
            return

        if exc_value is not None and (fut := self._fut) is not None:
            fut.set_exception(exc_value)

        state = self._disk_cache._state
        await state.release_write_barrier(exc_type, exc_value, traceback)
        await state.delete_future(self._key)

    def new_file_access(self, key: str) -> _ExclusiveFileAccess:
        return _ExclusiveFileAccess(
            self._disk_cache,
            self._disk_cache._shard_path(key),
        )

    def is_acquired(self) -> bool:
        return self._is_acquired

    def set_data(self, data: bytes | None) -> None:
        if (fut := self._fut) is None or fut.done():
            return

        fut.set_result(data)

    async def get_data(self) -> bytes | None:
        if (fut := self._fut) is None:
            return None

        return await asyncio.wait_for(fut, timeout=5.0)


class DiskCache:

    def __init__(
        self,
        root_dir: str,
        max_concurrency: int,
        disk_max_size: int,
        file_max_size: int,
    ):
        self._dir = Path(root_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state = _CoalescedAccessState(max_concurrency)
        self._disk_max_size = disk_max_size
        self._file_max_size = file_max_size

    def _shard_path(self, key_hex: str) -> Path:
        return self._dir / key_hex[:2] / key_hex[2:4] / f"{key_hex}.gz"

    def _lock_path(self, path: Path) -> Path:
        return path.with_suffix(".gz.lock")

    def _atomic_write(self, target: Path, contents: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp.write(contents)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        os.replace(tmp_path, target)

    def _read_disk(self, path: Path) -> bytes | None:
        try:
            with gzip.open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except Exception:
            with contextlib.suppress(Exception):
                path.unlink(missing_ok=True)

            return None

    def _write_disk(self, path: Path, contents: bytes) -> None:
        file_max_size = self._file_max_size

        if len(contents) > file_max_size:
            raise ValueError(
                f"Cache entry too large: {len(contents)} > {file_max_size}"
            )

        compressed = gzip.compress(contents, compresslevel=3)
        self._atomic_write(path, compressed)

    def read_data(self, key: str) -> bytes | None:
        return self._read_disk(self._shard_path(key))

    def new_coalesced_access(self, key: str) -> _CoalescedAccess:
        return _CoalescedAccess(self, key)

    def _enforce_disk_size_limit(self) -> None:
        total = 0
        files: list[tuple[float, Path, int]] = []

        for p in self._dir.rglob("*.gz"):
            try:
                st = p.stat()
            except FileNotFoundError:
                continue

            total += st.st_size
            files.append((st.st_mtime, p, st.st_size))

        disk_max_size = self._disk_max_size

        if total <= disk_max_size:
            return

        for _, p, sz in sorted(files, key=lambda x: x[0]):
            with contextlib.suppress(Exception):
                p.unlink(missing_ok=True)
                total -= sz

            if total <= disk_max_size:
                break

    async def clear(self) -> None:
        await self._state.clear()

        for child in self._dir.iterdir():
            with contextlib.suppress(Exception):
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
