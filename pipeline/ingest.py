"""
Push pipeline results to the Cloudflare Worker API.
"""

import asyncio
import logging

import httpx

from config import WORKER_URL, PIPELINE_API_KEY

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_RETRIES = 3


def _headers() -> dict:
    return {
        'Content-Type': 'application/json',
        'X-Pipeline-Key': PIPELINE_API_KEY
    }


async def _post_with_retry(client: httpx.AsyncClient, path: str, payload: dict) -> dict:
    """POST to the worker with exponential backoff retry."""
    url = f'{WORKER_URL}{path}'
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload, headers=_headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            if attempt == MAX_RETRIES - 1:
                logger.error(f'Failed to POST {path} after {MAX_RETRIES} attempts: {e}')
                raise
            wait = 2 ** attempt
            logger.warning(f'POST {path} failed (attempt {attempt + 1}), retrying in {wait}s: {e}')
            await asyncio.sleep(wait)
    return {}


async def push_papers(papers: list[dict]) -> int:
    """Push papers to /api/ingest/papers in batches. Returns total inserted."""
    total = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            result = await _post_with_retry(client, '/api/ingest/papers', {'papers': batch})
            total += result.get('inserted', 0)
            logger.debug(f'Pushed papers batch {i // BATCH_SIZE + 1}: {result}')
    return total


async def push_metrics(papers: list[dict]) -> int:
    """Push metrics for each paper to /api/ingest/metrics."""
    metrics = []
    for p in papers:
        metrics.append({
            'paper_id': p.get('arxiv_id') or p.get('id'),
            'citation_count': p.get('citation_count', 0),
            'citation_velocity': p.get('citation_velocity', 0),
            'influential_citations': p.get('influential_citations', 0),
            'altmetric_score': p.get('altmetric_score', 0),
            'news_count': p.get('news_count', 0),
            'twitter_count': p.get('twitter_count', 0),
            'patent_count': p.get('patent_count', 0),
            'wikipedia_count': p.get('wikipedia_count', 0),
            'fields_of_study': p.get('fields_of_study', []),
            'openalex_concepts': p.get('openalex_concepts', []),
            'h_index_avg': p.get('h_index_avg', 0),
            'composite_score': p.get('composite_score', 0),
            'factor_breakdown': p.get('factor_breakdown', {})
        })

    total = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(metrics), BATCH_SIZE):
            batch = metrics[i:i + BATCH_SIZE]
            result = await _post_with_retry(client, '/api/ingest/metrics', {'metrics': batch})
            total += result.get('inserted', 0)
    return total


async def push_summaries(summaries: list[dict]) -> int:
    """Push AI summaries to /api/ingest/summaries."""
    total = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(summaries), BATCH_SIZE):
            batch = summaries[i:i + BATCH_SIZE]
            result = await _post_with_retry(client, '/api/ingest/summaries', {'summaries': batch})
            total += result.get('inserted', 0)
    return total


async def push_digest(date: str, ranked_papers: list[dict]) -> int:
    """Create the daily digest ranking."""
    rankings = [
        {'paper_id': p.get('arxiv_id') or p.get('id'), 'rank': i + 1, 'composite_score': p['composite_score']}
        for i, p in enumerate(ranked_papers)
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await _post_with_retry(client, '/api/ingest/digest', {'date': date, 'rankings': rankings})
    return result.get('inserted', 0)


async def push_leaderboard(snapshot_date: str, list_type: str, ranked_papers: list[dict]) -> int:
    """Push a leaderboard snapshot (foundations or momentum) to /api/ingest/leaderboard."""
    entries = [
        {
            'paper_id': p.get('arxiv_id') or p.get('id'),
            'rank': i + 1,
            'citation_count': p.get('citation_count', 0),
            'score': p.get('momentum_score') if list_type == 'momentum' else None,
        }
        for i, p in enumerate(ranked_papers)
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await _post_with_retry(
            client, '/api/ingest/leaderboard',
            {'snapshot_date': snapshot_date, 'list_type': list_type, 'entries': entries}
        )
    return result.get('inserted', 0)


async def log_pipeline_start() -> int:
    """Log pipeline start. Returns run_id."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await _post_with_retry(client, '/api/pipeline/status', {'action': 'start'})
    return result.get('run_id', 0)


async def log_pipeline_complete(run_id: int, stats: dict, status: str = 'success', error: str | None = None):
    """Log pipeline completion."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        await _post_with_retry(client, '/api/pipeline/status', {
            'action': 'complete',
            'run_id': run_id,
            'status': status,
            'papers_fetched': stats.get('papers_fetched', 0),
            'papers_scored': stats.get('papers_scored', 0),
            'papers_summarized': stats.get('papers_summarized', 0),
            'error_message': error,
            'stats': stats
        })
