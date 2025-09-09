import asyncio
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
