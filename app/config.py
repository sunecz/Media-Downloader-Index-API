from dataclasses import dataclass
from typing import cast
from dynaconf import Dynaconf, Validator
from dynaconf.validator import ValidatorList

_dynaconf = Dynaconf(
    envvar_prefix="APP",
    load_dotenv=False,
    settings_files=[],  # Use ENV vars only
)

validators = cast(ValidatorList, _dynaconf.validators)
validators.register(Validator("database_url", cast=str, must_exist=True))
validators.register(Validator("db_pool_size", cast=int, default=10))
validators.register(Validator("db_max_overflow", cast=int, default=10))
validators.register(Validator("api_title", cast=str, must_exist=True))
validators.register(Validator("api_version", cast=str, must_exist=True))
validators.register(Validator("api_description", cast=str, must_exist=True))
validators.register(Validator("base_path", cast=str, must_exist=True))
validators.register(Validator("default_page_size", cast=int, default=10))
validators.register(Validator("max_page_size", cast=int, default=100))
validators.register(Validator("cache_dir", cast=str, must_exist=True))
validators.register(Validator("cache_hot_max_size", cast=int, default=1000))
validators.register(
    Validator("cache_disk_max_size", cast=int, default=10 * 1024 * 1024 * 1024)
)
validators.register(
    Validator("cache_file_max_size", cast=int, default=50 * 1024 * 1024)
)
validators.register(Validator("cache_max_concurrency", cast=int, default=8))
validators.validate()


@dataclass(frozen=True, slots=True)
class Config:
    database_url: str
    db_pool_size: int
    db_max_overflow: int
    api_title: str
    api_version: str
    api_description: str
    base_path: str
    default_page_size: int
    max_page_size: int
    cache_dir: str
    cache_hot_max_size: int
    cache_disk_max_size: int
    cache_file_max_size: int
    cache_max_concurrency: int


config = cast(Config, _dynaconf)
