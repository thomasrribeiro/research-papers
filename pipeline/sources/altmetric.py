"""
Enrich papers with social attention scores from the Altmetric API.
Free API: https://api.altmetric.com/  (no key needed for basic lookups)
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.altmetric.com/v1'
RATE_LIMIT_DELAY = 1.0  # Altmetric free tier: ~1 req/s


async def enrich_papers(papers: list[dict]) -> list[dict]:
    """
    Add altmetric_score, news_count, twitter_count, patent_count,
    wikipedia_count to each paper dict.
    """
    for p in papers:
        p.setdefault('altmetric_score', 0.0)
        p.setdefault('news_count', 0)
        p.setdefault('twitter_count', 0)
        p.setdefault('patent_count', 0)
        p.setdefault('wikipedia_count', 0)

    arxiv_papers = [p for p in papers if p.get('arxiv_id') or p.get('id')]
    logger.info(f'Enriching {len(arxiv_papers)} papers from Altmetric')

    async with httpx.AsyncClient(timeout=15.0) as client:
        for paper in arxiv_papers:
            arxiv_id = paper.get('arxiv_id') or paper.get('id')
            try:
                resp = await client.get(f'{BASE_URL}/arxiv/{arxiv_id}')
                if resp.status_code == 200:
                    data = resp.json()
                    paper['altmetric_score'] = float(data.get('score', 0) or 0)
                    counts = data.get('counts', {})
                    paper['news_count'] = int(counts.get('news', {}).get('posts_count', 0) or 0)
                    paper['twitter_count'] = int(counts.get('twitter', {}).get('posts_count', 0) or 0)
                    paper['patent_count'] = int(counts.get('patent', {}).get('posts_count', 0) or 0)
                    paper['wikipedia_count'] = int(counts.get('wikipedia', {}).get('posts_count', 0) or 0)
                elif resp.status_code == 404:
                    pass  # No Altmetric record — common for new/niche papers
                elif resp.status_code == 429:
                    logger.warning('Altmetric rate limit hit, sleeping 30s')
                    await asyncio.sleep(30)
                else:
                    logger.debug(f'Altmetric returned {resp.status_code} for {arxiv_id}')
            except httpx.HTTPError as e:
                logger.debug(f'Altmetric error for {arxiv_id}: {e}')

            await asyncio.sleep(RATE_LIMIT_DELAY)

    return papers
