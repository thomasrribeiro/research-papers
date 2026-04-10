"""
Enrich papers with concept tags from the OpenAlex API.
Docs: https://docs.openalex.org/
"""

import asyncio
import logging

import httpx

from config import OPENALEX_EMAIL

logger = logging.getLogger(__name__)

BASE_URL = 'https://api.openalex.org'
RATE_LIMIT_DELAY = 0.1  # OpenAlex polite pool is generous


async def enrich_papers(papers: list[dict]) -> list[dict]:
    """
    Add openalex_concepts to each paper dict.
    Looks up by arXiv ID using OpenAlex filter.
    """
    headers = {'User-Agent': f'research-papers/1.0 (mailto:{OPENALEX_EMAIL})'}

    for p in papers:
        p.setdefault('openalex_concepts', [])

    arxiv_ids = [p.get('arxiv_id') or p.get('id') for p in papers if p.get('arxiv_id') or p.get('id')]
    id_to_paper = {(p.get('arxiv_id') or p.get('id')): p for p in papers}

    logger.info(f'Enriching {len(arxiv_ids)} papers from OpenAlex')

    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        # Batch in groups of 25 using filter
        batch_size = 25
        for i in range(0, len(arxiv_ids), batch_size):
            batch = arxiv_ids[i:i + batch_size]
            filter_str = '|'.join(f'arxiv:{aid}' for aid in batch)

            try:
                resp = await client.get(
                    f'{BASE_URL}/works',
                    params={
                        'filter': f'ids.openalex:{filter_str}' if False else f'doi:{filter_str}',
                        'select': 'id,ids,concepts',
                        'per-page': batch_size
                    }
                )
                # OpenAlex supports arxiv filter directly
                resp = await client.get(
                    f'{BASE_URL}/works',
                    params={
                        'filter': ','.join(f'locations.landing_page_url:arxiv.org/abs/{aid}' for aid in batch[:1]),
                        'select': 'id,ids,concepts,referenced_works_count',
                        'per-page': batch_size
                    }
                )
                if resp.status_code != 200:
                    logger.debug(f'OpenAlex returned {resp.status_code} for batch')
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    continue

                data = resp.json()
                results = data.get('results', [])

                for work in results:
                    # Try to match by arXiv ID in the ids field
                    ids_obj = work.get('ids', {})
                    arxiv_url = ids_obj.get('arxiv', '')
                    if arxiv_url:
                        aid = arxiv_url.replace('https://arxiv.org/abs/', '').strip()
                        if aid in id_to_paper:
                            concepts = [
                                c['display_name']
                                for c in (work.get('concepts') or [])
                                if c.get('level', 99) <= 1  # top-level concepts only
                            ]
                            id_to_paper[aid]['openalex_concepts'] = concepts

            except httpx.HTTPError as e:
                logger.warning(f'OpenAlex error: {e}')

            await asyncio.sleep(RATE_LIMIT_DELAY)

    return papers
