"""
Fetch top-cited papers from OpenAlex and rank them two ways:
  - Foundations: raw all-time citation count (classic canon)
  - Momentum:   log-composite favoring recent velocity and acceleration

Uses OpenAlex (no API key required) via the polite-pool email header.
"""

import asyncio
import logging
import math
import os
import re
from datetime import date
from pathlib import Path

import httpx
import yaml

from config import LEADERBOARD_CONCEPTS, LEADERBOARD_SIZE, OPENALEX_EMAIL, SEMANTIC_SCHOLAR_API_KEY

logger = logging.getLogger(__name__)

OPENALEX_URL = 'https://api.openalex.org/works'
RESULTS_PER_CONCEPT = 200   # OpenAlex max per page; we fetch up to OPENALEX_PAGES pages per concept
OPENALEX_PAGES = 2          # 2 × 200 = 400 candidates per concept

S2_BASE = 'https://api.semanticscholar.org/graph/v1'
S2_FIELDS = (
    'paperId,externalIds,title,abstract,year,citationCount,'
    'fieldsOfStudy,openAccessPdf,publicationDate,authors'
)
S2_PER_QUERY = 200
RATE_LIMIT_S2 = 2.0  # conservative without API key (free tier: ~100 req/5 min)
# Broad queries that surface the canonical literature in each domain.
# S2 merges arXiv + conference + journal versions into one record, so AIAYN/BERT/etc.
# appear here with their true combined citation count.
S2_QUERIES = [
    'machine learning',
    'deep learning neural network',
    'transformer attention mechanism natural language processing',
    'computer vision image recognition object detection',
    'reinforcement learning policy gradient reward',
    'protein structure prediction genomics sequencing',
    'quantum mechanics condensed matter physics',
    'economics finance econometrics',
    'statistical inference Bayesian methods',
    'clinical trials medicine epidemiology',
]

RECENT_WINDOW_YEARS = 2
MAX_PLAUSIBLE_CITATIONS = 450_000  # hard ceiling — above this it's a data-aggregation error
# Age-aware cap: even the fastest-growing real papers don't exceed ~25k cites/year.
# Floor of 80k protects very-recent breakthrough papers.
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

    abstract = _HTML_TAG_RE.sub('', _reconstruct_abstract(work.get('abstract_inverted_index')))

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
        logger.warning(f'Dropping data error (hard cap): {title[:60]!r} has {citation_count} cites')
        return None

    pub_year_str = work.get('publication_date') or work.get('publication_year') or ''
    try:
        pub_year = int(str(pub_year_str)[:4])
    except (ValueError, TypeError):
        pub_year = date.today().year
    age_cap = max(80_000, 25_000 * max(1, date.today().year - pub_year))
    if citation_count > age_cap:
        logger.warning(f'Dropping data error (age cap {age_cap}): {title[:60]!r} has {citation_count} cites')
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


def _parse_s2_paper(item: dict) -> dict | None:
    """Convert a Semantic Scholar paper dict to our standard paper dict."""
    title = _HTML_TAG_RE.sub('', (item.get('title') or '')).strip()
    if not title:
        return None

    paper_id = item.get('paperId')
    if not paper_id:
        return None

    external_ids = item.get('externalIds') or {}
    doi = external_ids.get('DOI') or ''
    arxiv_id = external_ids.get('ArXiv') or ''

    # Prefer arXiv ID as DB key (consistent with feed papers); fall back to S2 ID
    db_id = arxiv_id if arxiv_id else f'S2:{paper_id}'

    abstract = _HTML_TAG_RE.sub('', (item.get('abstract') or '')).strip()

    pub_date = item.get('publicationDate') or ''
    if not pub_date:
        year = item.get('year')
        pub_date = f'{year}-01-01' if year else ''
    elif len(pub_date) > 10:
        pub_date = pub_date[:10]

    authors = []
    for a in (item.get('authors') or [])[:20]:
        name = a.get('name', '')
        if name:
            authors.append({'name': name, 'affiliation': ''})

    fields = item.get('fieldsOfStudy') or []
    primary_category = fields[0] if fields else 'General'

    pdf_info = item.get('openAccessPdf') or {}
    pdf_url = pdf_info.get('url') or (f'https://doi.org/{doi}' if doi else '')

    citation_count = item.get('citationCount') or 0
    if citation_count > MAX_PLAUSIBLE_CITATIONS:
        logger.warning(f'S2: dropping data error: {title[:60]!r} has {citation_count} cites')
        return None

    return {
        'id': db_id,
        'arxiv_id': db_id,
        's2_id': paper_id,
        'doi': doi or None,
        'title': title,
        'abstract': abstract,
        'authors': authors,
        'published_date': pub_date,
        'updated_date': None,
        'categories': fields,
        'primary_category': primary_category,
        'pdf_url': pdf_url,
        'citation_count': citation_count,
        'counts_by_year': [],  # S2 doesn't provide per-year data; momentum score will be 0 for S2-only
        'source': 'leaderboard_s2',
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


async def fetch_openalex_pool() -> list[dict]:
    """
    Fetch a large candidate pool of highly-cited papers from OpenAlex across all
    relevant concepts. Fetches up to OPENALEX_PAGES pages per concept.
    Returns a deduplicated list — no ranking applied.
    """
    all_papers: dict[str, dict] = {}  # openalex_id → paper
    target_concept_ids = frozenset(LEADERBOARD_CONCEPTS)

    select_fields = (
        'id,title,abstract_inverted_index,doi,publication_date,'
        'authorships,cited_by_count,counts_by_year,primary_location,concepts'
    )

    # Include preprints and reviews — many landmark ML papers are preprints or review articles.
    # Exclude only clearly non-paper types (books, datasets, editorials, errata).
    type_filter = 'article|preprint|review|book-chapter|conference-paper'

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={'User-Agent': f'ResearchPapersPipeline/1.0 (mailto:{OPENALEX_EMAIL})'}
    ) as client:
        for concept_id in LEADERBOARD_CONCEPTS:
            for page in range(1, OPENALEX_PAGES + 1):
                params = {
                    'sort': 'cited_by_count:desc',
                    'filter': f'concepts.id:{concept_id},is_paratext:false,type:{type_filter}',
                    'per-page': RESULTS_PER_CONCEPT,
                    'page': page,
                    'select': select_fields,
                    'mailto': OPENALEX_EMAIL,
                }
                try:
                    resp = await client.get(OPENALEX_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as e:
                    logger.warning(f'OpenAlex fetch failed for concept {concept_id} p{page}: {e}')
                    await asyncio.sleep(2.0)
                    break

                results = data.get('results') or []
                logger.info(f'OpenAlex concept {concept_id} p{page}: {len(results)} papers')

                added = 0
                for work in results:
                    paper = _parse_openalex_work(work)
                    if not paper or paper['id'] in all_papers:
                        continue
                    # Concept-score guard: the paper must score ≥ 0.15 on at least one
                    # of our target concepts. This drops tangentially-tagged glitches
                    # (e.g. a Turkish reproductive-health paper somehow tagged "Physics").
                    work_concepts = work.get('concepts') or []
                    if work_concepts:
                        has_target = any(
                            c.get('id', '').replace('https://openalex.org/', '') in target_concept_ids
                            and (c.get('score') or 0) >= 0.15
                            for c in work_concepts
                        )
                        if not has_target:
                            continue
                    all_papers[paper['id']] = paper
                    added += 1

                if len(results) < RESULTS_PER_CONCEPT:
                    break  # fewer results than requested means we're on the last page

                await asyncio.sleep(1.0)  # polite pool rate limit

    logger.info(f'OpenAlex pool: {len(all_papers)} unique papers')
    return list(all_papers.values())


async def fetch_semantic_scholar_pool() -> list[dict]:
    """
    Query Semantic Scholar /paper/search/bulk across broad topic queries, sorted by
    citation count. S2 merges arXiv + conference + journal versions into a single
    record, so papers like AIAYN/BERT/Adam appear here with their true combined cites.
    Returns a deduplicated list by S2 paperId.
    """
    all_papers: dict[str, dict] = {}  # db_id → paper
    headers = {'x-api-key': SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {}

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        for query in S2_QUERIES:
            params = {
                'query': query,
                'fields': S2_FIELDS,
                'sort': 'citationCount:desc',
                'limit': S2_PER_QUERY,
            }
            try:
                resp = await client.get(f'{S2_BASE}/paper/search/bulk', params=params)
                if resp.status_code == 429:
                    logger.warning('S2 rate limit; sleeping 60s')
                    await asyncio.sleep(60)
                    resp = await client.get(f'{S2_BASE}/paper/search/bulk', params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.warning(f'S2 search failed for {query!r}: {e}')
                await asyncio.sleep(RATE_LIMIT_S2 * 3)
                continue

            results = data.get('data') or []
            logger.info(f'S2 query {query!r}: {len(results)} papers')

            for item in results:
                paper = _parse_s2_paper(item)
                if paper and paper['id'] not in all_papers:
                    all_papers[paper['id']] = paper

            await asyncio.sleep(RATE_LIMIT_S2)

    logger.info(f'S2 pool: {len(all_papers)} unique papers')
    return list(all_papers.values())


async def load_landmark_seeds() -> list[dict]:
    """
    Load curated landmark papers from landmark_papers.yaml and fetch live citation
    data for each from Semantic Scholar. Papers not found via S2 are skipped silently.
    """
    yaml_path = Path(__file__).parent / 'landmark_papers.yaml'
    if not yaml_path.exists():
        logger.warning('landmark_papers.yaml not found; skipping seed list')
        return []

    with open(yaml_path) as f:
        seeds = yaml.safe_load(f) or []

    logger.info(f'Loading {len(seeds)} landmark seeds from YAML')
    headers = {'x-api-key': SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {}

    papers: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        for seed in seeds:
            arxiv_id = seed.get('arxiv_id', '')
            doi = seed.get('doi', '')
            if not arxiv_id and not doi:
                continue

            # Build S2 paper ID reference
            if arxiv_id:
                s2_ref = f'ARXIV:{arxiv_id}'
            else:
                s2_ref = f'DOI:{doi}'

            try:
                resp = await client.get(
                    f'{S2_BASE}/paper/{s2_ref}',
                    params={'fields': S2_FIELDS},
                )
                if resp.status_code == 404:
                    logger.debug(f'S2 not found: {seed.get("title", s2_ref)[:60]}')
                    continue
                if resp.status_code == 429:
                    await asyncio.sleep(60)
                    continue
                resp.raise_for_status()
                item = resp.json()
            except httpx.HTTPError as e:
                logger.warning(f'S2 seed lookup failed for {s2_ref}: {e}')
                await asyncio.sleep(RATE_LIMIT_S2)
                continue

            paper = _parse_s2_paper(item)
            if paper:
                papers.append(paper)

            await asyncio.sleep(RATE_LIMIT_S2 * 0.5)  # half-rate for single lookups

    logger.info(f'Loaded {len(papers)} landmark seed papers')
    return papers


async def fetch_candidate_pool() -> list[dict]:
    """
    Merge OpenAlex + Semantic Scholar discovery pools + curated landmark seeds,
    deduplicated by DOI or arXiv ID.
    OpenAlex records are preferred when both sources have the same paper (OpenAlex
    provides counts_by_year which is required for the Momentum score).
    """
    openalex_papers, s2_papers, seed_papers = await asyncio.gather(
        fetch_openalex_pool(),
        fetch_semantic_scholar_pool(),
        load_landmark_seeds(),
    )

    # Build lookup sets from the OpenAlex pool (preferred source for counts_by_year)
    oa_doi_set: set[str] = {p['doi'].lower() for p in openalex_papers if p.get('doi')}
    oa_id_set: set[str] = {p['id'].lower() for p in openalex_papers}

    def _is_in_oa(p: dict) -> bool:
        doi = (p.get('doi') or '').lower()
        return (doi and doi in oa_doi_set) or p['id'].lower() in oa_id_set

    s2_only = [p for p in s2_papers if not _is_in_oa(p)]
    seed_only = [p for p in seed_papers if not _is_in_oa(p) and
                 p['id'].lower() not in {x['id'].lower() for x in s2_only}]

    merged = openalex_papers + s2_only + seed_only
    logger.info(
        f'Merged pool: {len(openalex_papers)} OpenAlex + {len(s2_only)} S2-only + '
        f'{len(seed_only)} seed-only = {len(merged)} total'
    )
    return merged


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
