"""
Initial seed script — fetches the last N days of papers to populate the DB.
Run once before the daily cron takes over.

Usage:
    cd pipeline && python seed.py
"""

import asyncio
import logging
import sys
from datetime import date, timedelta
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import SEED_LOOKBACK_DAYS, DAILY_TOP_N
from sources.arxiv import fetch_recent_papers
from sources.semantic_scholar import enrich_papers as enrich_semantic_scholar
from sources.altmetric import enrich_papers as enrich_altmetric
from scoring import score_papers
from summarizer import summarize_papers
from ingest import push_papers, push_metrics, push_summaries, push_digest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s — %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger('seed')


async def run_seed():
    lookback_hours = SEED_LOOKBACK_DAYS * 24
    logger.info(f'=== Seed: fetching last {SEED_LOOKBACK_DAYS} days of papers ===')

    # Fetch a larger batch for seeding
    papers = await fetch_recent_papers(lookback_hours=lookback_hours)
    logger.info(f'Fetched {len(papers)} papers')

    if not papers:
        logger.warning('No papers fetched')
        return

    # Enrich (skip OpenAlex for speed during seed)
    logger.info('Enriching with Semantic Scholar...')
    papers = await enrich_semantic_scholar(papers)
    logger.info('Enriching with Altmetric...')
    papers = await enrich_altmetric(papers)

    # Score
    logger.info('Scoring...')
    papers = score_papers(papers)

    # Push all papers + metrics
    logger.info('Pushing to Worker...')
    await push_papers(papers)
    await push_metrics(papers)

    # Group by date and create daily digests
    from collections import defaultdict
    by_date: dict[str, list[dict]] = defaultdict(list)
    for p in papers:
        pub = p.get('published_date', date.today().isoformat())
        by_date[pub].append(p)

    for d, day_papers in sorted(by_date.items()):
        day_papers.sort(key=lambda p: p['composite_score'], reverse=True)
        top = day_papers[:DAILY_TOP_N]
        await push_digest(d, top)
        logger.info(f'  Digest {d}: {len(top)} papers')

    # Summarize today's top papers
    today = date.today().isoformat()
    today_papers = sorted(by_date.get(today, papers[:DAILY_TOP_N]),
                          key=lambda p: p['composite_score'], reverse=True)[:DAILY_TOP_N]
    logger.info(f'Summarizing {len(today_papers)} top papers for today...')
    summaries = await summarize_papers(today_papers)
    if summaries:
        await push_summaries(summaries)

    logger.info(f'=== Seed complete: {len(papers)} papers across {len(by_date)} dates ===')


if __name__ == '__main__':
    asyncio.run(run_seed())
