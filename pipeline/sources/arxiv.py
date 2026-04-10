"""
Fetch papers from the arXiv API.
Docs: https://info.arxiv.org/help/api/index.html
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from config import ARXIV_CATEGORIES, ARXIV_LOOKBACK_HOURS

logger = logging.getLogger(__name__)

ARXIV_API_URL = 'http://export.arxiv.org/api/query'
BATCH_SIZE = 100  # max arXiv returns per request
RATE_LIMIT_DELAY = 3.0  # seconds between requests (arXiv asks for ≥3s)

NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'arxiv': 'http://arxiv.org/schemas/atom',
    'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'
}


async def fetch_recent_papers(
    categories: list[str] | None = None,
    lookback_hours: int = ARXIV_LOOKBACK_HOURS
) -> list[dict]:
    """Fetch papers published within the last `lookback_hours` across all categories."""
    cats = categories or ARXIV_CATEGORIES
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    seen_ids: set[str] = set()
    papers: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for category in cats:
            logger.info(f'Fetching arXiv category: {category}')
            batch = await _fetch_category(client, category, since, seen_ids)
            papers.extend(batch)
            logger.info(f'  Got {len(batch)} new papers from {category}')
            await asyncio.sleep(RATE_LIMIT_DELAY)

    logger.info(f'Total unique papers fetched: {len(papers)}')
    return papers


async def _fetch_category(
    client: httpx.AsyncClient,
    category: str,
    since: datetime,
    seen_ids: set[str]
) -> list[dict]:
    """Fetch all recent papers from a single arXiv category."""
    papers = []
    start = 0

    while True:
        params = {
            'search_query': f'cat:{category}',
            'sortBy': 'submittedDate',
            'sortOrder': 'descending',
            'start': start,
            'max_results': BATCH_SIZE
        }

        try:
            resp = await client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning(f'arXiv API error for {category} at offset {start}: {e}')
            break

        entries, total = _parse_feed(resp.text)

        if not entries:
            break

        page_papers = []
        stop = False
        for entry in entries:
            published = entry.get('published_date')
            if published and _parse_date(published) < since:
                stop = True
                break
            arxiv_id = entry.get('arxiv_id', '')
            if arxiv_id and arxiv_id not in seen_ids:
                seen_ids.add(arxiv_id)
                page_papers.append(entry)

        papers.extend(page_papers)

        if stop or start + BATCH_SIZE >= total or len(entries) < BATCH_SIZE:
            break

        start += BATCH_SIZE
        await asyncio.sleep(RATE_LIMIT_DELAY)

    return papers


def _parse_feed(xml_text: str) -> tuple[list[dict], int]:
    """Parse arXiv Atom feed XML into paper dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f'Failed to parse arXiv feed: {e}')
        return [], 0

    total_elem = root.find('opensearch:totalResults', NS)
    total = int(total_elem.text) if total_elem is not None and total_elem.text else 0

    papers = []
    for entry in root.findall('atom:entry', NS):
        paper = _parse_entry(entry)
        if paper:
            papers.append(paper)

    return papers, total


def _parse_entry(entry: ET.Element) -> dict | None:
    """Parse a single Atom entry into a paper dict."""
    id_elem = entry.find('atom:id', NS)
    if id_elem is None or not id_elem.text:
        return None

    # Extract arXiv ID from URL (e.g. http://arxiv.org/abs/2401.12345v1)
    raw_id = id_elem.text.strip()
    arxiv_id = re.sub(r'v\d+$', '', raw_id.split('/abs/')[-1])

    title_elem = entry.find('atom:title', NS)
    title = ' '.join((title_elem.text or '').split()) if title_elem is not None else ''

    abstract_elem = entry.find('atom:summary', NS)
    abstract = ' '.join((abstract_elem.text or '').split()) if abstract_elem is not None else ''

    published_elem = entry.find('atom:published', NS)
    published_date = published_elem.text[:10] if published_elem is not None and published_elem.text else ''

    updated_elem = entry.find('atom:updated', NS)
    updated_date = updated_elem.text[:10] if updated_elem is not None and updated_elem.text else None

    # Authors
    authors = []
    for author_elem in entry.findall('atom:author', NS):
        name_elem = author_elem.find('atom:name', NS)
        if name_elem is not None and name_elem.text:
            authors.append({'name': name_elem.text.strip(), 'affiliation': ''})

    # Categories
    categories = []
    primary_category = ''
    primary_elem = entry.find('arxiv:primary_category', NS)
    if primary_elem is not None:
        primary_category = primary_elem.get('term', '')
        categories.append(primary_category)
    for cat_elem in entry.findall('atom:category', NS):
        term = cat_elem.get('term', '')
        if term and term not in categories:
            categories.append(term)

    # PDF URL
    pdf_url = None
    for link in entry.findall('atom:link', NS):
        if link.get('title') == 'pdf':
            pdf_url = link.get('href', '').replace('http://', 'https://')
            break
    if not pdf_url:
        pdf_url = f'https://arxiv.org/pdf/{arxiv_id}'

    if not title or not abstract or not arxiv_id:
        return None

    return {
        'id': arxiv_id,
        'arxiv_id': arxiv_id,
        'doi': None,
        'title': title,
        'abstract': abstract,
        'authors': authors,
        'published_date': published_date,
        'updated_date': updated_date,
        'categories': categories,
        'primary_category': primary_category or (categories[0] if categories else ''),
        'pdf_url': pdf_url,
        'source': 'arxiv'
    }


def _parse_date(date_str: str) -> datetime:
    """Parse ISO date string to timezone-aware datetime."""
    try:
        return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
