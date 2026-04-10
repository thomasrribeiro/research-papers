"""
Fetch recent preprints from bioRxiv and medRxiv.
API docs: https://api.biorxiv.org/

Each server has the same endpoint pattern:
  GET https://api.biorxiv.org/details/{server}/{from_date}/{to_date}/{cursor}/json
  GET https://api.biorxiv.org/details/medrxiv/{from_date}/{to_date}/{cursor}/json

Returns papers in the same shape as sources/arxiv.py so they merge cleanly into
the main pipeline.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.biorxiv.org/details'
PAGE_SIZE = 100  # bioRxiv API returns max 100 per page
RATE_LIMIT = 1.0  # seconds between requests
SERVERS = ['biorxiv', 'medrxiv']


async def fetch_recent_papers(
    lookback_hours: int = 48,
    servers: list[str] | None = None,
) -> list[dict]:
    """
    Fetch preprints posted in the last `lookback_hours` from bioRxiv and medRxiv.
    Returns a deduplicated list in the standard paper dict shape.
    """
    srv_list = servers or SERVERS
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    from_date = since.strftime('%Y-%m-%d')
    to_date = date.today().strftime('%Y-%m-%d')

    seen_dois: set[str] = set()
    papers: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for server in srv_list:
            batch = await _fetch_server(client, server, from_date, to_date, seen_dois)
            papers.extend(batch)
            logger.info(f'bioRxiv/{server}: {len(batch)} papers ({from_date} → {to_date})')
            await asyncio.sleep(RATE_LIMIT)

    logger.info(f'bioRxiv/medRxiv total: {len(papers)} unique papers')
    return papers


async def _fetch_server(
    client: httpx.AsyncClient,
    server: str,
    from_date: str,
    to_date: str,
    seen_dois: set[str],
) -> list[dict]:
    """Paginate through one server's date range and collect paper dicts."""
    papers: list[dict] = []
    cursor = 0

    while True:
        url = f'{BASE_URL}/{server}/{from_date}/{to_date}/{cursor}/json'
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning(f'bioRxiv {server} fetch error at cursor {cursor}: {e}')
            break

        collection = data.get('collection') or []
        if not collection:
            break

        for item in collection:
            paper = _parse_item(item, server)
            if not paper:
                continue
            doi = paper.get('doi') or paper['id']
            if doi in seen_dois:
                continue
            seen_dois.add(doi)
            papers.append(paper)

        # Pagination: API returns 100/page; keep going until fewer than PAGE_SIZE
        if len(collection) < PAGE_SIZE:
            break
        cursor += PAGE_SIZE
        await asyncio.sleep(RATE_LIMIT)

    return papers


def _parse_item(item: dict, server: str) -> dict | None:
    """Convert a bioRxiv/medRxiv API item to our standard paper dict."""
    title = (item.get('title') or '').strip()
    abstract = (item.get('abstract') or '').strip()
    doi = (item.get('doi') or '').strip()

    if not title or not doi:
        return None

    # Use DOI as the paper ID (stable, unique)
    paper_id = doi

    # Authors: API gives a semicolon-separated string, e.g. "Zhang, J.; Li, X."
    raw_authors = item.get('authors') or ''
    authors = [
        {'name': name.strip(), 'affiliation': ''}
        for name in raw_authors.split(';')
        if name.strip()
    ]
    # Add corresponding author institution if available
    if authors and item.get('author_corresponding_institution'):
        authors[0]['affiliation'] = item['author_corresponding_institution']

    pub_date = (item.get('date') or '')[:10]

    # Category → primary_category (e.g. "neuroscience", "infectious-diseases")
    category = (item.get('category') or '').replace('-', ' ').title()
    primary_category = category or server.capitalize()

    # PDF URL from DOI (bioRxiv always has a PDF)
    pdf_url = f'https://www.biorxiv.org/content/{doi}.full.pdf' if server == 'biorxiv' \
        else f'https://www.medrxiv.org/content/{doi}.full.pdf'

    return {
        'id': paper_id,
        'arxiv_id': paper_id,   # used as DB primary key
        'doi': doi,
        'title': title,
        'abstract': abstract,
        'authors': authors,
        'published_date': pub_date,
        'updated_date': None,
        'categories': [category] if category else [server.capitalize()],
        'primary_category': primary_category,
        'pdf_url': pdf_url,
        'source': server,       # 'biorxiv' or 'medrxiv'
    }
