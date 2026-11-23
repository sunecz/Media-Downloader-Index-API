from __future__ import annotations
import asyncio
import hashlib
from litestar.enums import ScopeType
from litestar.middleware.base import ASGIMiddleware
from litestar.response.base import ASGIResponse
from litestar.types import ASGIApp, Message, Receive, Scope, Send
import msgspec
from typing import Callable, Awaitable
from urllib.parse import urlsplit
from w3lib.url import canonicalize_url
from app.cache import LRUCache, DiskCache
from app.config import config
from app.db import engine, get_dataset_version
import logging

logger = logging.getLogger(__name__)

_version: int | None = None
_version_lock = asyncio.Lock()

_cache_lru = LRUCache(
    capacity=config.cache_hot_max_size,
)

_cache_disk = DiskCache(
    root_dir=config.cache_dir,
    max_concurrency=config.cache_max_concurrency,
    disk_max_size=config.cache_disk_max_size,
    file_max_size=config.cache_file_max_size,
    evict_target=config.cache_disk_evict_target,
)


async def start_cache() -> None:
    await asyncio.to_thread(_cache_disk.start)


async def stop_cache() -> None:
    await asyncio.to_thread(_cache_disk.stop)


def _version_is_higher(new: int | None, cur: int | None) -> bool:
    return new is not None and (cur is None or new > cur)


def _set_version(new: int | None) -> None:
    global _version
    _version = new


async def _ensure_cache_version(incoming: int | None) -> None:
    if not _version_is_higher(incoming, _version):
        return  # Fast path, no locking or IO

    async with _version_lock:
        if not _version_is_higher(incoming, _version):
            return

        # Memory caches are per process, the disk cache is shared and only
        # the first process to see the new version switches it.
        await _cache_lru.clear()
        await _cache_disk.clear_inflight()

        if await asyncio.to_thread(_cache_disk.ensure_version, incoming):
            logger.info("Disk cache switched to version %s", incoming)

        # Set only after the disk switch, so that no entry of the new version
        # is written before it
        _set_version(incoming)


def _normalize_uri(uri: str) -> str:
    canonical_uri = canonicalize_url(uri)
    parts = urlsplit(canonical_uri)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


# Bump when the response of a URI changes for the same dataset version
_KEY_FORMAT = 2


def _make_key(version: int | None, uri: str) -> str:
    material = msgspec.json.encode({
        "format": _KEY_FORMAT,
        "uri": _normalize_uri(uri),
        "version": "" if version is None else version,
    })

    return hashlib.sha256(material).hexdigest()


async def _get_data(
    fn: Callable[[str], Awaitable[bytes | None]],
    version: int | None,
    uri: str,
) -> bytes | None:
    await _ensure_cache_version(version)
    key = _make_key(version, uri)

    if (data := await _cache_lru.get(key)) is not None:
        return data

    if (data := await _cache_disk.read(version, key)) is not None:
        await _cache_lru.set(key, data)
        return data

    async with _cache_disk.new_coalesced_access(key) as access:
        if access.is_acquired():
            data = None

            try:
                # Another worker may be computing the same entry, wait for it
                async with _cache_disk.key_lock(key) as lock:
                    if (data := await _cache_disk.read(version, key)) is None:
                        # None = do not cache
                        if (data := await fn(uri)) is not None:
                            # The writer releases the lock once the entry is on disk
                            _cache_disk.enqueue(version, key, data, lock.detach())

                if data is not None:
                    await _cache_lru.set(key, data)
            finally:
                access.set_data(data)
        else:
            data = await access.get_data()

    return data


async def _get_version() -> int | None:
    async with engine.connect() as conn:
        return await get_dataset_version(conn)


class CacheMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP, ScopeType.ASGI)

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        next_app: ASGIApp,
    ) -> None:
        is_sent = False

        try:
            uri = scope.get("raw_path") or scope["path"]
            uri = uri if isinstance(uri, str) else uri.decode()

            if scope.get("query_string"):
                uri = f"{uri}?{scope['query_string'].decode()}"

            version = await _get_version()

            async def get_data(uri: str) -> bytes | None:
                nonlocal is_sent
                is_sent = True
                status_code: int | None = None
                chunks: list[bytes] = []

                async def send_wrapper(message: Message) -> None:
                    nonlocal status_code

                    if message["type"] == "http.response.start":
                        status_code = message["status"]
                    elif message["type"] == "http.response.body":
                        chunks.append(message.get("body", b""))

                    await send(message)

                await next_app(scope, receive, send_wrapper)

                # Hits are replayed as 200
                return b"".join(chunks) if status_code == 200 else None

            data = await _get_data(get_data, version, uri)

            if is_sent:
                return  # Bytes already sent

            if data is None:
                # The awaited response was not cacheable
                await next_app(scope, receive, send)
                return

            response = ASGIResponse(
                status_code=200,
                headers={
                    "Content-Type": "application/json",
                },
                body=data,
            )

            await response(scope, receive, send)
        except Exception as e:
            logger.exception(e)

            if not is_sent:
                await next_app(scope, receive, send)
