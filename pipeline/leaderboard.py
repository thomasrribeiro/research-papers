"""
Fetch top-cited papers from OpenAlex and rank them two ways:
  - Foundations: raw all-time citation count (classic canon)
  - Momentum:   log-composite favoring recent velocity and acceleration

Uses OpenAlex (no API key required) via the polite-pool email header.
"""

import asyncio
import logging
import math
import re
from datetime import date

import httpx

from config import LEADERBOARD_CONCEPTS, LEADERBOARD_SIZE, OPENALEX_EMAIL

logger = logging.getLogger(__name__)

OPENALEX_URL = 'https://api.openalex.org/works'
RESULTS_PER_CONCEPT = 200  # fetch a larger pool so momentum has candidates outside the raw top-50

RECENT_WINDOW_YEARS = 2
MAX_PLAUSIBLE_CITATIONS = 450_000  # OpenAlex occasionally has data-aggregation glitches; no real paper exceeds this
_HTML_TAG_RE = re.compile(r'<[^>]+>')


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
    title = _HTML_TAG_RE.sub('', (work.get('title') or '')).strip()
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

    citation_count = work.get('cited_by_count', 0) or 0
    if citation_count > MAX_PLAUSIBLE_CITATIONS:
        logger.warning(f'Dropping suspected data error: {title[:60]!r} has {citation_count} cites')
        return None

    # Yearly breakdown — list of {year, cited_by_count}
    counts_by_year = work.get('counts_by_year') or []

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
        'counts_by_year': counts_by_year,
        'source': 'leaderboard',
    }


def _compute_momentum_score(paper: dict) -> float:
    """
    Multiplicative score rewarding papers that are both currently hot AND
    outpacing their own historical average.

    hot      = log1p(recent_citations_last_2y)     # absolute heat
    velocity = recent_citations / RECENT_WINDOW_YEARS  # per-year, recent
    avg_hist = total_citations / years_old          # per-year, lifetime avg
    momentum = velocity / avg_hist                  # acceleration ratio

    score    = hot × sqrt(max(momentum, 0.1))

    Neither term can dominate: a paper must be hot AND have momentum.
    sqrt(momentum) softens the penalty for steady classics (~1.0 ratio)
    while strongly depressing decelerating work (ratio ~0.1-0.3).
    """
    total = paper.get('citation_count', 0) or 0
    if total < 1000:
        return 0.0

    pub_date = paper.get('published_date') or ''
    try:
        pub_year = int(pub_date[:4]) if pub_date else date.today().year
    except ValueError:
        pub_year = date.today().year

    current_year = date.today().year
    years_old = max(1, current_year - pub_year)
    if years_old < 2:
        return 0.0

    # Sum citations in the last RECENT_WINDOW_YEARS *complete* years (exclude current partial year)
    counts = paper.get('counts_by_year') or []
    recent_cutoff = current_year - RECENT_WINDOW_YEARS  # e.g., 2024 if current is 2026
    recent_citations = sum(
        (entry.get('cited_by_count') or 0)
        for entry in counts
        if recent_cutoff <= (entry.get('year') or 0) < current_year
    )
    if recent_citations == 0:
        return 0.0

    velocity = recent_citations / RECENT_WINDOW_YEARS
    avg_hist = total / years_old
    momentum = velocity / max(avg_hist, 1.0)

    hot = math.log1p(recent_citations)
    return hot * math.sqrt(max(momentum, 0.1))


async def fetch_candidate_pool() -> list[dict]:
    """
    Fetch a large candidate pool of highly-cited papers across all relevant concepts.
    Returns a deduplicated list — no ranking applied.
    """
    all_papers: dict[str, dict] = {}  # openalex_id → paper

    select_fields = (
        'id,title,abstract_inverted_index,doi,publication_date,'
        'authorships,cited_by_count,counts_by_year,primary_location,concepts'
    )

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={'User-Agent': f'ResearchPapersPipeline/1.0 (mailto:{OPENALEX_EMAIL})'}
    ) as client:
        for concept_id in LEADERBOARD_CONCEPTS:
            params = {
                'sort': 'cited_by_count:desc',
                'filter': f'concepts.id:{concept_id},is_paratext:false,type:article',
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

    logger.info(f'Candidate pool: {len(all_papers)} unique papers')
    return list(all_papers.values())


def rank_foundations(pool: list[dict], limit: int = LEADERBOARD_SIZE) -> list[dict]:
    """Rank the candidate pool by raw all-time citation count."""
    sorted_papers = sorted(pool, key=lambda p: p.get('citation_count', 0) or 0, reverse=True)
    return sorted_papers[:limit]


def rank_momentum(pool: list[dict], limit: int = LEADERBOARD_SIZE) -> list[dict]:
    """Rank the candidate pool by the momentum composite score."""
    scored = []
    for p in pool:
        p['momentum_score'] = _compute_momentum_score(p)
        scored.append(p)
    sorted_papers = sorted(scored, key=lambda p: p.get('momentum_score', 0.0), reverse=True)
    return sorted_papers[:limit]
