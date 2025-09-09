from typing import Annotated
from litestar.params import Parameter
from msgspec import Struct, Meta


class Pagination(Struct):
    page: Annotated[int | None, Parameter(
        description="Page number")] = None
    size: Annotated[int | None, Parameter(
        description="Page size")] = None


class Program(Struct):
    source: Annotated[str, Meta(description="Source of the program")]
    uri: Annotated[str, Meta(description="URI of the program")]
    title: Annotated[str, Meta(description="Title of the program")]
    type: Annotated[str, Meta(
        description="Type of the program (e.g. movie, tv_series)")]


class ProgramList(Struct):
    programs: Annotated[list[Program], Meta(description="List of programs")]
    total: Annotated[int, Meta(description="Total number of programs")]
    pagination: Annotated[Pagination, Meta(
        description="Pagination parameters")]
