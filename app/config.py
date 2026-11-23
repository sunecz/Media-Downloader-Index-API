import os
from typing import Annotated
import msgspec
from msgspec import Meta, Struct

_ENV_PREFIX = "APP_"


class Config(Struct, frozen=True, kw_only=True):
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 10
    api_title: str
    api_version: str
    api_description: str
    base_path: str
    default_page_size: int = 10
    max_page_size: int = 100
    cache_dir: str
    cache_hot_max_size: int = 1000
    cache_disk_max_size: int = 10 * 1024 * 1024 * 1024
    cache_file_max_size: int = 50 * 1024 * 1024
    cache_max_concurrency: int = 8
    cache_disk_evict_target: Annotated[float, Meta(gt=0, lt=1)] = 0.7


def _load() -> Config:
    env = {
        name.removeprefix(_ENV_PREFIX).lower(): value
        for name, value in os.environ.items()
        if name.startswith(_ENV_PREFIX)
    }

    try:
        # strict=False converts the strings to int and float
        return msgspec.convert(env, Config, strict=False)
    except msgspec.ValidationError as e:
        raise RuntimeError(f"Invalid configuration: {e}") from None


config = _load()
