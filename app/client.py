import asyncio
from typing import Iterable, cast, overload
from rdflib import Literal, URIRef
import httpx
import msgspec
from app.config import config

_gate = asyncio.Semaphore(200)
_client: httpx.AsyncClient | None = None


async def start_client():
    global _client
    _client = httpx.AsyncClient(
        base_url=config.database_url,
        limits=httpx.Limits(
            max_keepalive_connections=200,
            max_connections=400,
        ),
        timeout=httpx.Timeout(
            timeout=10.0,
            connect=5.0,
        ),
        headers={"Accept": "application/sparql-results+json"},
        http2=False,
    )


async def stop_client():
    if (client := _client) is None:
        return

    await client.aclose()


def sparql_literal(text: str, lang: str | None = None, datatype: str | None = None) -> str:
    return Literal(text, lang=lang, datatype=datatype).n3()


def sparql_iri(iri: str) -> str:
    return URIRef(iri).n3()


async def sparql_run_query(query: str) -> dict:
    if (client := _client) is None:
        return {}

    async with _gate:
        result = await client.post(
            "/sparql",
            content=query.encode("utf-8"),
            headers={"Content-Type": "application/sparql-query"},
        )

    result.raise_for_status()
    return msgspec.json.decode(result.content)


async def sparql_query_results(query: str) -> Iterable[dict]:
    data = await sparql_run_query(query)
    head = data.get("head", {}).get("vars", [])
    rows = data.get("results", {}).get("bindings", [])

    return (
        {v: cell.get("value", "") for v, cell in row.items() if v in head}
        for row in rows
    )


@overload
async def sparql_query_get_value[T](
    query: str,
    name: str,
    default: None = None,
    *,
    _type: type[T],
) -> T:
    ...


@overload
async def sparql_query_get_value[T, D](
    query: str,
    name: str,
    default: D,
    *,
    _type: type[T] | None = None,
) -> T | D:
    ...


async def sparql_query_get_value[T, D](
    query: str,
    name: str,
    default: D | None = None,
    *,
    _type: type[T] | None = None,
) -> T | D | None:
    result = await sparql_query_results(query)

    try:
        first_row = next(iter(result))
        return cast(T | D, first_row.get(name, default))
    except (StopIteration, IndexError, ValueError):
        return default
