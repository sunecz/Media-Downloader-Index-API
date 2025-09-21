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
from app.client import sparql_query_get_value
from app.config import config
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
)


def _version_is_higher(new: int | None, cur: int | None) -> bool:
    return new is not None and (cur is None or new > cur)


def _set_version(new: int | None) -> None:
    global _version
    _version = new


async def _ensure_cache_version(incoming: int | None) -> None:
    async with _version_lock:
        if _version_is_higher(incoming, _version):
            await _clear_all_caches()
            _set_version(incoming)


async def _clear_all_caches() -> None:
    await _cache_lru.clear()
    await _cache_disk.clear()


def _normalize_uri(uri: str) -> str:
    canonical_uri = canonicalize_url(uri)
    parts = urlsplit(canonical_uri)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _make_key(version: int | None, uri: str) -> str:
    material = msgspec.json.encode({
        "uri": _normalize_uri(uri),
        "version": "" if version is None else version,
    })

    return hashlib.sha256(material).hexdigest()


async def _get_data(
    fn: Callable[[str], Awaitable[bytes]],
    version: int | None,
    uri: str,
) -> bytes | None:
    await _ensure_cache_version(version)
    key = _make_key(version, uri)

    if (data := await _cache_lru.get(key)) is not None:
        return data

    if (data := _cache_disk.read_data(key)) is not None:
        await _cache_lru.set(key, data)
        return data

    async with _cache_disk.new_coalesced_access(key) as access:
        if access.is_acquired():
            try:
                with access.new_file_access(key) as file:
                    if (data := file.get_data()) is None:
                        data = await fn(uri)
                        file.set_data(data)

                await _cache_lru.set(key, data)
            finally:
                access.set_data(data)
        else:
            data = await access.get_data()

    return data


async def _get_version() -> int | None:
    query = f"""
    PREFIX mdig: <https://schema.mdi.sune.app/graph#>

    SELECT ?version {{
        GRAPH <urn:x-arq:DefaultGraph#meta> {{
            <urn:x-arq:DefaultGraph> mdig:version ?version
        }}
    }}
    """

    return await sparql_query_get_value(query, 'version', None)


class CacheMiddleware(ASGIMiddleware):
    scopes = (ScopeType.HTTP, ScopeType.ASGI)

    async def handle(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        next_app: ASGIApp,
    ) -> None:
        try:
            uri = scope.get("raw_path") or scope["path"]
            uri = uri if isinstance(uri, str) else uri.decode()

            if scope.get("query_string"):
                uri = f"{uri}?{scope['query_string'].decode()}"

            version = await _get_version()
            is_cached = True

            async def get_data(uri: str) -> bytes:
                nonlocal is_cached
                is_cached = False
                chunks: list[bytes] = []

                async def send_wrapper(message: Message) -> None:
                    if message["type"] == "http.response.body":
                        chunks.append(message.get("body", b""))

                    await send(message)

                await next_app(scope, receive, send_wrapper)
                return b"".join(chunks)

            data = await _get_data(get_data, version, uri)

            if not is_cached:
                return  # Bytes already sent

            response = ASGIResponse(
                status_code=200,
                headers={
                    "Content-Type": "application/json",
                },
                body=data or b"",
            )

            await response(scope, receive, send)
        except Exception as e:
            logger.exception(e)
            await next_app(scope, receive, send)
