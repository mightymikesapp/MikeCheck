"""Semantic search tool for legal cases.

This module implements the "Smart Scout" strategy:
1. Fetch candidates from CourtListener (broad keyword search)
2. Fetch full text for candidates
3. Embed and store in local vector store
4. Perform semantic search to re-rank and find best matches
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from fastmcp import FastMCP

from app.logging_config import tool_logging
from app.mcp_client import get_client
from app.mcp_types import ToolPayload

if TYPE_CHECKING:  # pragma: no cover
    from app.analysis.search.vector_store import LegalVectorStore

# Initialize tool
search_server: FastMCP[ToolPayload] = FastMCP("Legal Research Search")

_vector_store_instance: "LegalVectorStore | None" = None


def get_vector_store() -> LegalVectorStore:
    """Lazily initialize and return the LegalVectorStore instance.

    This allows tests to inject a mock before this is called.
    """
    global _vector_store_instance

    if _vector_store_instance is None:
        # Runtime import to avoid circular dependencies or initialization costs
        from app.analysis.search.vector_store import LegalVectorStore

        _vector_store_instance = LegalVectorStore(persistence_path="./data/chroma_db")

    return _vector_store_instance


def set_vector_store(store: LegalVectorStore) -> None:
    """Override the vector store instance (for testing)."""
    global _vector_store_instance
    _vector_store_instance = store


logger = logging.getLogger(__name__)


async def _fetch_full_text_safe(client: Any, case_id: str) -> tuple[str, str | None]:
    """Helper to fetch full text safely and return (id, text)."""
    try:
        full_text = await client.get_opinion_full_text(int(case_id))
        return case_id, full_text
    except Exception as e:
        logger.warning(f"Failed to fetch text for case {case_id}: {e}")
        return case_id, None


async def semantic_search_impl(query: str, limit: int = 10) -> dict[str, Any]:
    """Perform a semantic search for legal cases (implementation).

    Args:
        query: Conceptual search query
        limit: Number of results to return

    Returns:
        Dictionary with re-ranked search results and statistics
    """
    client = get_client()
    vector_store = get_vector_store()

    # Step 1: Broad Sweep - Search CourtListener
    candidate_limit = max(20, limit * 3)
    logger.info(f"Step 1: Fetching {candidate_limit} candidates for query: {query}")

    search_results = await client.search_opinions(
        q=query,
        limit=candidate_limit,
        order_by="score desc",
    )

    raw_candidates = search_results.get("results")
    if raw_candidates is None:
        return {
            "query": query,
            "results": [],
            "stats": {
                "candidates_found": 0,
                "full_texts_fetched": 0,
                "indexed_count": 0,
                "total_library_size": vector_store.count(),
            },
        }

    if not isinstance(raw_candidates, list):
        logger.warning("Unexpected search response shape; no candidates to process")
        return {
            "query": query,
            "results": [],
            "stats": {
                "candidates_found": 0,
                "full_texts_fetched": 0,
                "indexed_count": 0,
                "total_library_size": vector_store.count(),
            },
        }

    candidates: list[Mapping[str, object]] = [
        candidate for candidate in raw_candidates if isinstance(candidate, Mapping)
    ]
    logger.info(f"Found {len(candidates)} candidates")

    # Step 2 & 3: Enrichment & Indexing
    candidate_ids: list[str] = []
    case_map: dict[str, Mapping[str, object]] = {}

    for c in candidates:
        cid = c.get("id")
        if cid is None and c.get("opinions"):
            opinions = c.get("opinions")
            if isinstance(opinions, Sequence) and opinions:
                first_opinion = opinions[0]
                if isinstance(first_opinion, Mapping):
                    cid = first_opinion.get("id")
        # If no ID found, skip this candidate
        if cid:
            cid = str(cid)
            candidate_ids.append(cid)
            case_map[cid] = c

    # Check existing to avoid re-fetching
    existing_records = vector_store.collection.get(ids=candidate_ids, include=[])
    existing_ids: set[str] = set()
    if isinstance(existing_records, Mapping):
        record_ids = existing_records.get("ids")
        if isinstance(record_ids, list) and record_ids and isinstance(record_ids[0], list):
            existing_ids = {str(value) for value in record_ids[0] if value is not None}

    cases_to_fetch = []

    for cid in candidate_ids:
        if cid not in existing_ids:
            cases_to_fetch.append(cid)

    logger.info(f"Need to fetch full text for {len(cases_to_fetch)} new cases")

    # Batch fetch full texts
    full_text_fetches = 0
    documents = []
    metadatas = []
    ids = []

    # Fetch in batches of 5 to respect rate limits gracefully
    batch_size = 5
    for i in range(0, len(cases_to_fetch), batch_size):
        batch_ids = cases_to_fetch[i : i + batch_size]
        tasks = [_fetch_full_text_safe(client, cid) for cid in batch_ids]
        full_text_results = await asyncio.gather(*tasks)

        for cid, text in full_text_results:
            if not text:
                continue

            case = case_map.get(cid)
            if case is None:
                continue

            full_text_fetches += 1

            case_name = case.get("caseName") if isinstance(case.get("caseName"), str) else "Unknown"
            citations = case.get("citation")
            primary_citation = ""
            if isinstance(citations, list) and citations and isinstance(citations[0], str):
                primary_citation = citations[0]

            metadata = {
                "case_name": case_name,
                "citation": primary_citation,
                "date_filed": case.get("dateFiled", ""),
                "court": case.get("court", ""),
                "original_score": case.get("score", 0.0),
            }

            documents.append(text)
            metadatas.append(metadata)
            ids.append(cid)

    # Upsert to vector store
    if documents:
        logger.info(f"Step 3: Indexing {len(documents)} new cases")
        vector_store.add_documents(documents, metadatas, ids)

    # Step 4: Semantic Search (Re-ranking)
    logger.info("Step 4: Running semantic search")
    results = vector_store.search(query, limit=limit)

    # Step 5: Format Results
    formatted_results = []

    ids_result = results.get("ids")
    metadatas_result = results.get("metadatas")
    distances_result = results.get("distances")

    if (
        isinstance(ids_result, list)
        and ids_result
        and isinstance(ids_result[0], list)
        and isinstance(metadatas_result, list)
        and metadatas_result
        and isinstance(metadatas_result[0], list)
        and isinstance(distances_result, list)
        and distances_result
        and isinstance(distances_result[0], list)
    ):
        num_results = min(
            len(ids_result[0]),
            len(metadatas_result[0]),
            len(distances_result[0]),
        )
        for i in range(num_results):
            metadata_entry = metadatas_result[0][i]
            distance = distances_result[0][i]
            case_id = ids_result[0][i]

            if not isinstance(metadata_entry, Mapping):
                continue
            if not isinstance(distance, (int, float)):
                continue

            formatted_results.append(
                {
                    "case_name": metadata_entry.get("case_name"),
                    "citation": metadata_entry.get("citation"),
                    "similarity_score": 1.0 - float(distance),
                    "date_filed": metadata_entry.get("date_filed"),
                    "court": metadata_entry.get("court"),
                    "id": case_id,
                }
            )

    return {
        "query": query,
        "results": formatted_results,
        "stats": {
            "candidates_found": len(candidates),
            "full_texts_fetched": full_text_fetches,
            "indexed_count": len(documents),
            "total_library_size": vector_store.count(),
        },
    }


@search_server.tool()
@tool_logging("semantic_search")
async def semantic_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Perform a semantic search for legal cases.

    Uses a "Smart Scout" strategy:
    1. Broadly searches CourtListener API for candidates
    2. Fetches full text and indexes them locally
    3. Performs vector similarity search to find conceptually relevant cases

    Args:
        query: Conceptual search query (e.g., "landlord liability for dog bites")
        limit: Number of results to return

    Returns:
        Dictionary with re-ranked search results and statistics
    """
    return await semantic_search_impl(query, limit)


@search_server.tool()
@tool_logging("purge_memory")
def purge_memory() -> str:
    """Clear the local semantic search library (memory).

    Use this to free up disk space or start fresh.
    """
    vector_store = get_vector_store()
    count_before = vector_store.count()
    vector_store.clear()
    return f"Memory purged. Removed {count_before} cases from local library."


@search_server.tool()
@tool_logging("get_library_stats")
def get_library_stats() -> dict[str, Any]:
    """Get statistics about the local semantic search library."""
    vector_store = get_vector_store()
    return vector_store.get_stats()
