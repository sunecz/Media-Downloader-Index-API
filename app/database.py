from dataclasses import dataclass
import logging
from typing import Iterable
from rdflib import Literal, URIRef
from app.client import sparql_run_query
from app.models import CursorPaginationResult, Program, ProgramList
from app.utils import encode_cursor

logger = logging.getLogger(__name__)


@dataclass
class ProgramListPagination:
    size: int
    after_title: str | None = None
    after_uri: str | None = None


def sparql_literal(text: str, lang: str | None = None, datatype: str | None = None) -> str:
    return Literal(text, lang=lang, datatype=datatype).n3()


def sparql_iri(iri: str) -> str:
    return URIRef(iri).n3()


class DatabaseService:

    async def _run_query(self, query: str) -> Iterable[dict]:
        data = await sparql_run_query(query)
        head = data.get("head", {}).get("vars", [])
        rows = data.get("results", {}).get("bindings", [])

        return (
            {v: cell.get("value", "") for v, cell in row.items() if v in head}
            for row in rows
        )

    async def get_programs(
        self,
        source: str | None = None,
        pagination: ProgramListPagination | None = None,
    ) -> ProgramList:
        query = self._build_programs_query(source, pagination)
        results = await self._run_query(query)

        programs = self._parse_programs_results(results)
        total_count = len(programs)

        size = total_count
        next_cursor = None

        if pagination is not None:
            list_size = total_count
            size = pagination.size
            total_count = await self._get_total_count(source)

            if list_size > size:
                programs = programs[:size]
                last_program = programs[-1]
                next_cursor = encode_cursor({
                    "title": last_program.title,
                    "uri": last_program.uri,
                })

        return ProgramList(
            programs=programs,
            total=total_count,
            pagination=CursorPaginationResult(
                size=size,
                next_cursor=next_cursor,
            )
        )

    def _build_programs_query(
        self,
        source: str | None = None,
        pagination: ProgramListPagination | None = None,
    ) -> str:
        paginate = ""
        limit = ""
        filters = ""

        if source:
            filters += f"""
            ?uri mdip:source {sparql_literal(source)} .
            """

        if pagination is not None:
            size = pagination.size
            after_title = pagination.after_title
            after_uri = pagination.after_uri

            if after_title and after_uri:
                lc_after_title = f"LCASE({sparql_literal(after_title)})"
                l_after_uri = sparql_iri(after_uri)

                # Performance note:
                #   In Fuseki it seems to be better to not bind the LCASE
                #   values using the BIND keyword, but rather keep repeating
                #   the expression.
                paginate = f"""
                FILTER (
                    (LCASE(?title) > {lc_after_title}) ||
                    (LCASE(?title) = {lc_after_title} && ?uri > {l_after_uri})
                )
                """

            # +1 to check if there are more items after the true limit
            limit = f"LIMIT {size + 1}"

        return f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX sch: <https://schema.org/>
        PREFIX mdip: <https://schema.mdi.sune.app/properties/>
        
        SELECT DISTINCT ?uri ?title ?type ?source
        WHERE {{
            ?uri mdip:source ?source ;
                 sch:name    ?title  ;
                 rdf:type    ?type   .
            {filters}
            {paginate}
        }}
        ORDER BY LCASE(?title) ?uri
        {limit}
        """

    async def _get_total_count(self, source: str | None = None) -> int:
        filters = ""

        if source:
            filters += f"""
            ?uri mdip:source {sparql_literal(source)} .
            """

        count_query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX sch: <https://schema.org/>
        PREFIX mdip: <https://schema.mdi.sune.app/properties/>
        
        SELECT (COUNT(DISTINCT ?uri) AS ?count)
        WHERE {{
            ?uri sch:name ?title ;
                 rdf:type ?type  .
            {filters}
        }}
        """

        result = await self._run_query(count_query)

        try:
            first_row = next(iter(result))
            return int(first_row.get('count', 0))
        except (StopIteration, IndexError, ValueError):
            return 0

    def _program_type(self, db_type: str) -> str:
        match db_type:
            case "https://schema.org/Movie":
                return "movie"
            case "https://schema.org/TVSeries":
                return "tv_series"
            case _:
                return "unknown"

    def _parse_programs_results(self, results: Iterable[dict]) -> list[Program]:
        return [
            Program(
                source=row.get("source", ""),
                uri=row.get("uri", ""),
                title=row.get("title", ""),
                type=self._program_type(row.get("type", ""))
            )
            for row in results
        ]
