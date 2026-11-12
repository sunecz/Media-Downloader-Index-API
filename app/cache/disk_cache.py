"""
On-disk response cache shared by all worker processes of one machine.

Layout of the root directory:

    .state                       Shared record: magic, dataset version, total bytes
    .evict.lock                  Held (non-blocking) by the single evicting process
    locks/<xx>.lock              Striped per-key locks, xx = first 2 chars of the key
    data/<version>/xx/yy/<key>.gz  Entries, one directory per dataset version

Coordination uses flock(2), which the kernel releases when a process dies, so
a crashed worker never leaves a stale lock behind. flock is not reliable on
network filesystems, the directory must be on a local volume.
"""
from __future__ import annotations
import asyncio
import contextlib
from dataclasses import dataclass
import fcntl
import gzip
import logging
import os
from pathlib import Path
import queue
import shutil
import struct
import tempfile
import threading
import time
from types import TracebackType
from typing import AsyncContextManager, AsyncIterator, Iterator

logger = logging.getLogger(__name__)

_STATE = struct.Struct("<8sqq")
_STATE_MAGIC = b"MDIC0001"
_VERSION_UNSET = -1

_QUEUE_MAX_SIZE = 1000
_KEY_LOCK_TIMEOUT = 5.0
_KEY_LOCK_DELAY_MIN = 0.02
_KEY_LOCK_DELAY_MAX = 0.2
# How long a request waits for another request of the same process
_COALESCED_WAIT_TIMEOUT = 5.0
# Older temporary files are leftovers of a crashed write
_TMP_MAX_AGE = 3600.0


def _version_number(version: int | None) -> int:
    return _VERSION_UNSET if version is None else version


def _release_lock(fd: int | None) -> None:
    if fd is None:
        return

    with contextlib.suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)

    with contextlib.suppress(OSError):
        os.close(fd)


def _remove_empty_dirs(path: Path, levels: int) -> None:
    for _ in range(levels):
        try:
            path.rmdir()
        except OSError:
            return  # Not empty or already gone

        path = path.parent


def _numeric_dirs(path: Path) -> list[tuple[int, Path]]:
    dirs: list[tuple[int, Path]] = []

    try:
        children = list(path.iterdir())
    except FileNotFoundError:
        return dirs

    for child in children:
        try:
            dirs.append((int(child.name), child))
        except ValueError:
            continue

    return dirs


class _SharedState:
    """
    The version and total size record shared by all processes. All methods
    block, call them from a thread, never from the event loop.
    """

    def __init__(self, path: Path):
        self._fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        # flock does not exclude threads sharing the same file descriptor
        self._mutex = threading.Lock()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            os.close(self._fd)

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        with self._mutex:
            fcntl.flock(self._fd, fcntl.LOCK_EX)

            try:
                yield
            finally:
                fcntl.flock(self._fd, fcntl.LOCK_UN)

    def _read(self) -> tuple[int, int] | None:
        raw = os.pread(self._fd, _STATE.size, 0)

        if len(raw) != _STATE.size:
            return None

        magic, version, total = _STATE.unpack(raw)
        return (version, total) if magic == _STATE_MAGIC else None

    def _write(self, version: int, total: int) -> None:
        os.pwrite(self._fd, _STATE.pack(_STATE_MAGIC, version, max(0, total)), 0)

    def _read_or_unset(self) -> tuple[int, int]:
        return self._read() or (_VERSION_UNSET, 0)

    def load(self, data_dir: Path) -> int:
        """Returns the current version, rebuilds the record if it is invalid."""
        with self._locked():
            if (record := self._read()) is not None:
                return record[0]

            # Keep the newest version's entries, the others are removed later
            versions = _numeric_dirs(data_dir)
            version = max((v for v, _ in versions), default=_VERSION_UNSET)
            total = 0

            for dirpath, _, names in os.walk(data_dir / str(version)):
                for name in names:
                    path = os.path.join(dirpath, name)

                    if name.endswith(".tmp"):
                        with contextlib.suppress(OSError):
                            os.unlink(path)
                    elif name.endswith(".gz"):
                        with contextlib.suppress(OSError):
                            total += os.stat(path).st_size

            self._write(version, total)
            logger.info("Rebuilt cache state: version=%d, total=%d", version, total)
            return version

    def snapshot(self) -> tuple[int, int]:
        with self._locked():
            return self._read_or_unset()

    def ensure_version(self, version: int) -> bool:
        """Switches to a higher version, returns True if this call did it."""
        with self._locked():
            current, _ = self._read_or_unset()

            if version <= current:
                return False

            self._write(version, 0)
            return True

    def commit(self, version: int, tmp_path: Path, final_path: Path) -> int | None:
        """
        Moves a written entry into place and accounts for its size. Returns
        the new total, or None if the entry belongs to an older version.
        Holding the lock during the rename guarantees that an entry never
        survives a version switch.
        """
        with self._locked():
            current, total = self._read_or_unset()

            if version < current:
                tmp_path.unlink(missing_ok=True)
                _remove_empty_dirs(tmp_path.parent, levels=3)
                return None

            try:
                old_size = final_path.stat().st_size
            except FileNotFoundError:
                old_size = 0

            try:
                new_size = tmp_path.stat().st_size
                os.replace(tmp_path, final_path)
            except FileNotFoundError:
                # The directory was removed meanwhile
                tmp_path.unlink(missing_ok=True)
                return None

            total += new_size - old_size
            self._write(current, total)
            return total

    def correct(self, version: int, start_total: int, measured: int, freed: int) -> int:
        """
        Replaces the counted total with the measured one, keeping the changes
        made by other processes since the measurement started.
        """
        with self._locked():
            current, total = self._read_or_unset()

            if current != version:
                return total  # Switched meanwhile, the total was reset

            total = max(0, total - start_total + measured - freed)
            self._write(current, total)
            return total


class _CoalescedAccessState:

    def __init__(self, max_concurrency: int):
        self._inflight: dict[str, asyncio.Future[bytes | None]] = {}
        self._inflight_lock = asyncio.Lock()
        self._compute_semaphore = asyncio.Semaphore(max_concurrency)

    async def get_future(self, key: str) -> asyncio.Future[bytes | None]:
        async with self._inflight_lock:
            if (fut := self._inflight.get(key)) is None:
                fut = asyncio.get_running_loop().create_future()
                self._inflight[key] = fut

        return fut

    async def delete_future(self, key: str) -> None:
        async with self._inflight_lock:
            self._inflight.pop(key, None)

    async def acquire_compute(self) -> None:
        await self._compute_semaphore.acquire()

    def release_compute(self) -> None:
        self._compute_semaphore.release()

    async def clear(self) -> None:
        async with self._inflight_lock:
            self._inflight.clear()


class _CoalescedAccess(AsyncContextManager):
    """Lets only one request per process compute a missing entry."""

    def __init__(self, state: _CoalescedAccessState, key: str):
        self._state = state
        self._key = key
        self._fut: asyncio.Future[bytes | None] | None = None
        self._is_acquired = False

    async def __aenter__(self) -> _CoalescedAccess:
        state = self._state
        fut = await state.get_future(self._key)
        self._fut = fut

        if not fut.done():
            await state.acquire_compute()
            is_acquired = not fut.done()
            self._is_acquired = is_acquired

            if not is_acquired:
                state.release_compute()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._is_acquired:
            return

        if exc_value is not None and (fut := self._fut) is not None and not fut.done():
            fut.set_exception(exc_value)
            # Mark as retrieved, there may be no waiter
            fut.exception()

        self._state.release_compute()
        await self._state.delete_future(self._key)

    def is_acquired(self) -> bool:
        return self._is_acquired

    def set_data(self, data: bytes | None) -> None:
        if (fut := self._fut) is None or fut.done():
            return

        fut.set_result(data)

    async def get_data(self) -> bytes | None:
        if (fut := self._fut) is None:
            return None

        return await asyncio.wait_for(asyncio.shield(fut), timeout=_COALESCED_WAIT_TIMEOUT)


class KeyLock:
    """A held (or, after a timeout, not held) cross-process lock of a key."""

    def __init__(self, fd: int | None):
        self._fd = fd

    def detach(self) -> int | None:
        """Transfers the ownership of the lock to the caller."""
        fd = self._fd
        self._fd = None
        return fd


@dataclass(slots=True)
class _WriteItem:
    version: int
    key: str
    data: bytes
    lock_fd: int | None


class DiskCache:

    def __init__(
        self,
        root_dir: str,
        max_concurrency: int,
        disk_max_size: int,
        file_max_size: int,
        evict_target: float,
    ):
        self._root = Path(root_dir)
        self._data_dir = self._root / "data"
        self._locks_dir = self._root / "locks"
        self._evict_lock_path = self._root / ".evict.lock"
        self._disk_max_size = disk_max_size
        self._file_max_size = file_max_size
        self._evict_size = int(disk_max_size * evict_target)
        self._inflight = _CoalescedAccessState(max_concurrency)
        self._queue: queue.Queue[_WriteItem | None] = queue.Queue(_QUEUE_MAX_SIZE)
        self._state: _SharedState | None = None
        self._writer: threading.Thread | None = None

    # ----- Lifecycle (blocking, run in a thread) -----

    def start(self) -> None:
        """Must run in each worker process, after it was started."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)

        state = _SharedState(self._root / ".state")
        self._state = state
        self._delete_versions_below(state.load(self._data_dir))

        writer = threading.Thread(
            target=self._run_writer,
            name="disk-cache-writer",
            daemon=True,
        )
        self._writer = writer
        writer.start()

    def stop(self, timeout: float = 5.0) -> None:
        if (writer := self._writer) is not None:
            with contextlib.suppress(queue.Full):
                self._queue.put(None, timeout=timeout)

            writer.join(timeout)
            self._writer = None

        if (state := self._state) is not None:
            state.close()
            self._state = None

    def ensure_version(self, version: int | None) -> bool:
        """
        Switches the cache to a higher version, exactly one process across
        all workers does it. Returns True if this call did it.
        """
        if version is None or (state := self._state) is None:
            return False

        if not state.ensure_version(version):
            return False

        self._delete_versions_below(version)
        return True

    # ----- Async API -----

    async def read(self, version: int | None, key: str) -> bytes | None:
        return await asyncio.to_thread(self._read_entry, self._entry_path(version, key))

    @contextlib.asynccontextmanager
    async def key_lock(self, key: str) -> AsyncIterator[KeyLock]:
        """
        Locks the key's stripe across processes. Polls instead of blocking a
        thread, gives up (yielding an unheld lock) after a timeout.
        """
        fd = os.open(self._locks_dir / f"{key[:2]}.lock", os.O_RDWR | os.O_CREAT, 0o644)
        acquired = False

        try:
            acquired = await self._acquire_lock(fd)
        finally:
            if not acquired:
                os.close(fd)

        lock = KeyLock(fd if acquired else None)

        try:
            yield lock
        finally:
            _release_lock(lock.detach())

    def enqueue(self, version: int | None, key: str, data: bytes, lock_fd: int | None) -> None:
        """
        Queues an entry to be written, the writer releases the lock once the
        entry is in place. Best effort, dropped if the queue is full.
        """
        item = _WriteItem(_version_number(version), key, data, lock_fd)

        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.warning("Cache write queue is full, dropping an entry")
            _release_lock(lock_fd)

    def new_coalesced_access(self, key: str) -> _CoalescedAccess:
        return _CoalescedAccess(self._inflight, key)

    async def clear_inflight(self) -> None:
        await self._inflight.clear()

    # ----- Internals -----

    def _entry_path(self, version: int | None, key: str) -> Path:
        return (
            self._data_dir / str(_version_number(version))
            / key[:2] / key[2:4] / f"{key}.gz"
        )

    @staticmethod
    async def _acquire_lock(fd: int) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _KEY_LOCK_TIMEOUT
        delay = _KEY_LOCK_DELAY_MIN

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                pass

            if loop.time() >= deadline:
                logger.warning("Timed out waiting for a cache key lock")
                return False

            await asyncio.sleep(delay)
            delay = min(delay * 2, _KEY_LOCK_DELAY_MAX)

    @staticmethod
    def _read_entry(path: Path) -> bytes | None:
        try:
            with gzip.open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except Exception:
            with contextlib.suppress(Exception):
                path.unlink(missing_ok=True)

            return None

    def _delete_versions_below(self, version: int) -> None:
        for number, path in _numeric_dirs(self._data_dir):
            if number < version:
                shutil.rmtree(path, ignore_errors=True)

    def _run_writer(self) -> None:
        while (item := self._queue.get()) is not None:
            try:
                self._write(item)
            except Exception:
                logger.exception("Failed to write a cache entry")
            finally:
                _release_lock(item.lock_fd)

    def _write(self, item: _WriteItem) -> None:
        if (state := self._state) is None:
            return

        if item.version < state.snapshot()[0]:
            return  # The cache switched to a newer version meanwhile

        if len(item.data) > self._file_max_size:
            logger.warning(
                "Cache entry too large: %d > %d", len(item.data), self._file_max_size
            )
            return

        final_path = self._entry_path(item.version, item.key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(item.data, compresslevel=3)

        # No fsync: a lost entry is recomputed, the rename prevents torn files
        fd, tmp_name = tempfile.mkstemp(dir=final_path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)

        try:
            with os.fdopen(fd, "wb") as f:
                f.write(compressed)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        total = state.commit(item.version, tmp_path, final_path)

        if total is not None and total > self._disk_max_size:
            self._evict(state)

    def _evict(self, state: _SharedState) -> None:
        fd = os.open(self._evict_lock_path, os.O_RDWR | os.O_CREAT, 0o644)

        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # Another process is evicting

            version, start_total = state.snapshot()
            now = time.time()
            files: list[tuple[float, str, int]] = []
            measured = 0

            for dirpath, _, names in os.walk(self._data_dir / str(version)):
                for name in names:
                    path = os.path.join(dirpath, name)

                    try:
                        st = os.stat(path)
                    except FileNotFoundError:
                        continue

                    if name.endswith(".tmp"):
                        if now - st.st_mtime > _TMP_MAX_AGE:
                            with contextlib.suppress(OSError):
                                os.unlink(path)
                    elif name.endswith(".gz"):
                        measured += st.st_size
                        files.append((st.st_mtime, path, st.st_size))

            files.sort()
            freed = 0
            count = 0

            for _, path, size in files:
                if measured - freed <= self._evict_size:
                    break

                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass  # Already gone, no longer occupies space
                except OSError:
                    continue

                freed += size
                count += 1

            total = state.correct(version, start_total, measured, freed)
            logger.info(
                "Cache eviction: removed %d files (%d bytes), total %d -> %d",
                count, freed, start_total, total,
            )
        finally:
            _release_lock(fd)
