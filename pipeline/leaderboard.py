"""
Fetch top-cited papers from OpenAlex for the Leaderboard.

Uses OpenAlex (no API key required) to retrieve the highest-cited papers
across the relevant disciplines, sorted by citation count descending.
"""

import asyncio
import logging

import httpx

from config import LEADERBOARD_CONCEPTS, LEADERBOARD_SIZE, OPENALEX_EMAIL

logger = logging.getLogger(__name__)

OPENALEX_URL = 'https://api.openalex.org/works'
RESULTS_PER_CONCEPT = 100  # fetch per concept, then deduplicate and truncate


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Reconstruct plain-text abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return ''
    positions: dict[int, str] = {}
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions[pos] = word
    return ' '.join(positions[i] for i in sorted(positions.keys()))


def _parse_openalex_work(work: dict) -> dict | None:
    """Convert an OpenAlex work dict to our standard paper dict."""
    title = (work.get('title') or '').strip()
    if not title:
        return None

    # Use OpenAlex ID as the paper_id (strip URL prefix: https://openalex.org/W...)
    openalex_id = work.get('id', '').replace('https://openalex.org/', '')
    doi = work.get('doi', '')
    if doi:
        doi = doi.replace('https://doi.org/', '')

    abstract = _reconstruct_abstract(work.get('abstract_inverted_index'))

    pub_date = work.get('publication_date') or ''
    if len(pub_date) > 10:
        pub_date = pub_date[:10]

    # Authors
    authors = []
    for authorship in (work.get('authorships') or [])[:20]:
        author = authorship.get('author') or {}
        institutions = authorship.get('institutions') or []
        affil = institutions[0].get('display_name', '') if institutions else ''
        name = author.get('display_name', '')
        if name:
            authors.append({'name': name, 'affiliation': affil})

    # Concepts / categories
    concepts = work.get('concepts') or []
    categories = [c.get('display_name', '') for c in concepts[:5] if c.get('display_name')]
    primary_category = categories[0] if categories else 'General'

    # PDF URL
    primary_location = work.get('primary_location') or {}
    pdf_url = primary_location.get('pdf_url') or ''
    if not pdf_url and doi:
        pdf_url = f'https://doi.org/{doi}'

    citation_count = work.get('cited_by_count', 0)

    return {
        'id': openalex_id,
        'arxiv_id': openalex_id,  # used as the DB primary key
        'doi': doi or None,
        'title': title,
        'abstract': abstract,
        'authors': authors,
        'published_date': pub_date,
        'updated_date': None,
        'categories': categories,
        'primary_category': primary_category,
        'pdf_url': pdf_url,
        'citation_count': citation_count,
        'source': 'leaderboard',
    }


async def fetch_top_cited(limit: int = LEADERBOARD_SIZE) -> list[dict]:
    """
    Fetch top-cited papers across key research domains using OpenAlex.
    Returns a deduplicated list sorted by citation_count descending.
    """
    all_papers: dict[str, dict] = {}  # openalex_id → paper

    select_fields = (
        'id,title,abstract_inverted_index,doi,publication_date,'
        'authorships,cited_by_count,primary_location,concepts'
    )

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={'User-Agent': f'ResearchPapersPipeline/1.0 (mailto:{OPENALEX_EMAIL})'}
    ) as client:
        for concept_id in LEADERBOARD_CONCEPTS:
            params = {
                'sort': 'cited_by_count:desc',
                'filter': f'concepts.id:{concept_id},is_paratext:false',
                'per-page': RESULTS_PER_CONCEPT,
                'select': select_fields,
                'mailto': OPENALEX_EMAIL,
            }
            try:
                resp = await client.get(OPENALEX_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.warning(f'OpenAlex fetch failed for concept {concept_id}: {e}')
                await asyncio.sleep(2.0)
                continue

            results = data.get('results') or []
            logger.info(f'OpenAlex concept {concept_id}: got {len(results)} papers')

            for work in results:
                paper = _parse_openalex_work(work)
                if paper and paper['id'] not in all_papers:
                    all_papers[paper['id']] = paper

            await asyncio.sleep(1.0)  # polite pool rate limit

    # Sort by citation_count descending, truncate to limit
    sorted_papers = sorted(all_papers.values(), key=lambda p: p.get('citation_count', 0), reverse=True)
    top = sorted_papers[:limit]

    logger.info(f'Leaderboard: {len(all_papers)} unique papers fetched, returning top {len(top)}')
    return top
