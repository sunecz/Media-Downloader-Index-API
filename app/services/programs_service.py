from dataclasses import dataclass
import logging
from typing import Iterable
from app.client import sparql_literal, sparql_query_get_value, sparql_query_results
from app.models import CursorPaginationResult, Program, ProgramList
from app.utils import encode_cursor, normalize_str

logger = logging.getLogger(__name__)


@dataclass
class ProgramListPagination:
    size: int
    after_title: str | None = None
    after_uri: str | None = None


class ProgramsService:

    def _query_get_programs(
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
                l_after_uri = sparql_literal(after_uri)

                # Performance note:
                #   In Fuseki it seems to be better to not bind the LCASE
                #   values using the BIND keyword, but rather keep repeating
                #   the expression.
                paginate = f"""
                FILTER (
                    (LCASE(?title) > {lc_after_title}) ||
                    (LCASE(?title) = {lc_after_title} && STR(?uri) > {l_after_uri})
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
        ORDER BY LCASE(?title) STR(?uri)
        {limit}
        """

    async def _query_get_programs_total(self, source: str | None = None) -> int:
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

        return int(await sparql_query_get_value(count_query, 'count', 0))

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

    async def get_programs(
        self,
        source: str | None = None,
        pagination: ProgramListPagination | None = None,
    ) -> ProgramList:
        query = self._query_get_programs(source, pagination)
        results = await sparql_query_results(query)

        programs = self._parse_programs_results(results)
        total_count = len(programs)

        size = total_count
        next_cursor = None

        if pagination is not None:
            list_size = total_count
            size = pagination.size
            total_count = await self._query_get_programs_total(source)

            if list_size > size:
                programs = programs[:size]
                last_program = programs[-1]
                next_cursor = encode_cursor({
                    "title": normalize_str(last_program.title),
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
