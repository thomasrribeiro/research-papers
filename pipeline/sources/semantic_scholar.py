"""
Enrich papers with citation data from the Semantic Scholar Academic Graph API.
Docs: https://api.semanticscholar.org/api-docs/
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from statistics import mean

import httpx

from config import SEMANTIC_SCHOLAR_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.semanticscholar.org/graph/v1'
# Fields to fetch for each paper
PAPER_FIELDS = (
    'paperId,externalIds,citationCount,influentialCitationCount,'
    'fieldsOfStudy,authors.authorId,authors.name,authors.hIndex,authors.paperCount,authors.affiliations'
)
BATCH_SIZE = 50  # S2 supports up to 500 per batch lookup, but keep small to avoid timeouts
RATE_LIMIT_FREE = 1.0   # seconds between requests without API key
RATE_LIMIT_KEYED = 0.1  # seconds with API key


def _make_s2_ref(paper_id: str) -> str:
    """Map an internal paper ID to the Semantic Scholar reference format.

    DOIs always start with '10.' — everything else is treated as an arXiv ID.
    S2 IDs (prefixed 'S2:') are stripped to raw hash.
    """
    if paper_id.startswith('10.'):
        return f'DOI:{paper_id}'
    if paper_id.startswith('S2:'):
        return paper_id[3:]
    return f'ARXIV:{paper_id}'


async def enrich_papers(papers: list[dict]) -> list[dict]:
    """
    Add citation_count, citation_velocity, influential_citations,
    fields_of_study, and h_index_avg to each paper dict.
    Returns the same list with added keys (in-place).
    """
    delay = RATE_LIMIT_KEYED if SEMANTIC_SCHOLAR_API_KEY else RATE_LIMIT_FREE
    headers = {'x-api-key': SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {}

    # Build two lookups:
    #   id_to_paper: internal paper ID (arxiv_id or doi-as-id) → paper
    #   doi_to_paper: normalised DOI → paper (for DOI-based matches in S2 response)
    id_to_paper: dict[str, dict] = {}
    doi_to_paper: dict[str, dict] = {}
    for p in papers:
        paper_id = p.get('arxiv_id') or p.get('id')
        if paper_id:
            id_to_paper[paper_id] = p
            # Initialise defaults so graceful degradation works
            p.setdefault('citation_count', 0)
            p.setdefault('citation_velocity', 0.0)
            p.setdefault('influential_citations', 0)
            p.setdefault('fields_of_study', [])
            p.setdefault('h_index_avg', 0.0)
        doi = (p.get('doi') or '').lower()
        if doi:
            doi_to_paper[doi] = p

    all_ids = list(id_to_paper.keys())
    logger.info(f'Enriching {len(all_ids)} papers from Semantic Scholar')

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        for i in range(0, len(all_ids), BATCH_SIZE):
            batch_ids = all_ids[i:i + BATCH_SIZE]
            # Use DOI: prefix for DOI-based IDs (bioRxiv), ARXIV: otherwise
            s2_ids = [_make_s2_ref(bid) for bid in batch_ids]

            try:
                resp = await client.post(
                    f'{BASE_URL}/paper/batch',
                    params={'fields': PAPER_FIELDS},
                    json={'ids': s2_ids}
                )
                if resp.status_code == 429:
                    logger.warning('Semantic Scholar rate limit hit, sleeping 60s')
                    await asyncio.sleep(60)
                    resp = await client.post(
                        f'{BASE_URL}/paper/batch',
                        params={'fields': PAPER_FIELDS},
                        json={'ids': s2_ids}
                    )
                resp.raise_for_status()
                results = resp.json()
            except httpx.HTTPError as e:
                logger.warning(f'Semantic Scholar batch error: {e}')
                await asyncio.sleep(delay * 5)
                continue

            for item in results:
                if not item:
                    continue
                ext_ids = item.get('externalIds') or {}
                arxiv_ext = ext_ids.get('ArXiv')
                doi_ext = (ext_ids.get('DOI') or '').lower()

                # Match by ArXiv ID first, then by DOI (covers bioRxiv papers whose
                # internal id *is* the DOI, e.g. '10.1101/759852')
                paper = None
                if arxiv_ext:
                    paper = id_to_paper.get(arxiv_ext)
                if paper is None and doi_ext:
                    paper = doi_to_paper.get(doi_ext) or id_to_paper.get(doi_ext)
                if paper is None:
                    continue
                paper['citation_count'] = item.get('citationCount') or 0
                paper['influential_citations'] = item.get('influentialCitationCount') or 0
                paper['fields_of_study'] = item.get('fieldsOfStudy') or []

                # Estimate citation velocity: influential_citations / months since publish
                pub_date = paper.get('published_date', '')
                paper['citation_velocity'] = _estimate_velocity(
                    paper['citation_count'], pub_date
                )

                # Author h-index average
                authors_data = item.get('authors') or []
                h_indices = [a.get('hIndex') or 0 for a in authors_data if a]
                paper['h_index_avg'] = mean(h_indices) if h_indices else 0.0

                # Merge author affiliations back into existing authors list
                existing_authors = paper.get('authors', [])
                for j, auth_data in enumerate(authors_data):
                    if j < len(existing_authors) and auth_data:
                        affiliations = auth_data.get('affiliations') or []
                        if affiliations:
                            existing_authors[j]['affiliation'] = affiliations[0] if affiliations else ''

            await asyncio.sleep(delay)

    return papers


def _estimate_velocity(citation_count: int, published_date: str) -> float:
    """Citations per month since publication (proxy for velocity)."""
    if not published_date or citation_count == 0:
        return 0.0
    try:
        pub = datetime.fromisoformat(published_date)
        months = max(1, (datetime.now() - pub).days / 30)
        return citation_count / months
    except ValueError:
        return 0.0
