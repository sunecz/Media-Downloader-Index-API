import logging
from typing import Iterable
from rdflib import Literal, URIRef
from app.client import sparql_run_query
from app.models import Program

logger = logging.getLogger(__name__)


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
        page: int | None = None,
        size: int | None = None,
    ) -> tuple[list[Program], int]:
        query = self._build_programs_query(source, page, size)
        results = await self._run_query(query)

        programs = self._parse_programs_results(results)
        total_count = len(programs)

        if page is not None and size is not None:
            total_count = await self._get_total_count(source)

        return programs, total_count

    def _build_programs_query(
        self,
        source: str | None = None,
        page: int | None = None,
        size: int | None = None,
    ) -> str:
        filters = []

        if source:
            filters.append(f"?uri mdip:source {sparql_literal(source)} .")

        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX sch: <https://schema.org/>
        PREFIX mdip: <https://schema.mdi.sune.app/properties/>
        
        SELECT DISTINCT ?uri ?title ?type ?source
        WHERE {{
            {"\n".join(filters)}
            ?uri mdip:source ?source ;
                 sch:name    ?title  ;
                 rdf:type    ?type   .
        }}
        ORDER BY LCASE(?title) ?title
        """

        if page is not None and size is not None:
            offset = (page - 1) * size
            query += f"\nLIMIT {size}\nOFFSET {offset}"

        return query

    async def _get_total_count(self, source: str | None = None) -> int:
        filters = []

        if source:
            filters.append(f"?uri mdip:source {sparql_literal(source)} .")

        count_query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX sch: <https://schema.org/>
        PREFIX mdip: <https://schema.mdi.sune.app/properties/>
        
        SELECT (COUNT(DISTINCT ?uri) AS ?count)
        WHERE {{
            {"\n".join(filters)}
            ?uri sch:name ?title ;
                 rdf:type ?type  .
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
