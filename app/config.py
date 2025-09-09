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
validators.register(Validator("api_title", cast=str, must_exist=True))
validators.register(Validator("api_version", cast=str, must_exist=True))
validators.register(Validator("api_description", cast=str, must_exist=True))
validators.register(Validator("base_path", cast=str, must_exist=True))
validators.register(Validator("default_page_size", cast=int, default=10))
validators.register(Validator("max_page_size", cast=int, default=100))
validators.validate()


@dataclass(frozen=True, slots=True)
class Config:
    database_url: str
    api_title: str
    api_version: str
    api_description: str
    base_path: str
    default_page_size: int
    max_page_size: int


config = cast(Config, _dynaconf)
