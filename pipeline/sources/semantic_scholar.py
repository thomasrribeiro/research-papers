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


async def enrich_papers(papers: list[dict]) -> list[dict]:
    """
    Add citation_count, citation_velocity, influential_citations,
    fields_of_study, and h_index_avg to each paper dict.
    Returns the same list with added keys (in-place).
    """
    delay = RATE_LIMIT_KEYED if SEMANTIC_SCHOLAR_API_KEY else RATE_LIMIT_FREE
    headers = {'x-api-key': SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {}

    # Build lookup: arxiv_id -> paper
    id_to_paper: dict[str, dict] = {}
    for p in papers:
        arxiv_id = p.get('arxiv_id') or p.get('id')
        if arxiv_id:
            id_to_paper[arxiv_id] = p
            # Initialise defaults so graceful degradation works
            p.setdefault('citation_count', 0)
            p.setdefault('citation_velocity', 0.0)
            p.setdefault('influential_citations', 0)
            p.setdefault('fields_of_study', [])
            p.setdefault('h_index_avg', 0.0)

    arxiv_ids = list(id_to_paper.keys())
    logger.info(f'Enriching {len(arxiv_ids)} papers from Semantic Scholar')

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        for i in range(0, len(arxiv_ids), BATCH_SIZE):
            batch_ids = arxiv_ids[i:i + BATCH_SIZE]
            s2_ids = [f'ARXIV:{aid}' for aid in batch_ids]

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
                arxiv_ext = (item.get('externalIds') or {}).get('ArXiv')
                if not arxiv_ext or arxiv_ext not in id_to_paper:
                    continue

                paper = id_to_paper[arxiv_ext]
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
