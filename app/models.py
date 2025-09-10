from typing import Annotated
from litestar.params import Parameter
from msgspec import Struct, Meta


class CursorPagination(Struct):
    cursor: Annotated[str | None, Parameter(
        description="Base64 encoded JSON cursor")] = None
    size: Annotated[int | None, Parameter(description="Page size")] = None


class DecodedCursorPagination(Struct):
    cursor: Annotated[dict, Parameter(description="JSON cursor")]
    size: Annotated[int, Parameter(description="Page size")]


class CursorPaginationResult(Struct):
    size: Annotated[int, Meta(description="Page size")]
    next_cursor: Annotated[str | None, Meta(description="Next cursor")]


class Program(Struct):
    source: Annotated[str, Meta(description="Source of the program")]
    uri: Annotated[str, Meta(description="URI of the program")]
    title: Annotated[str, Meta(description="Title of the program")]
    type: Annotated[str, Meta(
        description="Type of the program (e.g. movie, tv_series)")]


class ProgramList(Struct):
    programs: Annotated[list[Program], Meta(description="List of programs")]
    total: Annotated[int, Meta(description="Total number of programs")]
    pagination: Annotated[CursorPaginationResult, Meta(
        description="Pagination result")]
