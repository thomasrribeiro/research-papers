"""
Daily pipeline orchestrator.

Steps:
1. Log pipeline start
2. Fetch papers from arXiv (last 48h)
3. Enrich with Semantic Scholar (citation data, author h-index)
4. Enrich with OpenAlex (concept tags)
5. Enrich with Altmetric (social attention scores)
6. Compute composite scores
7. Push papers + metrics to Worker
8. Generate AI summaries for top N papers
9. Push summaries + daily digest to Worker
10. Log pipeline completion
"""

import asyncio
import logging
import sys
from datetime import date

# Allow running from the pipeline/ directory
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import DAILY_TOP_N, ARXIV_LOOKBACK_HOURS, LEADERBOARD_SIZE
from sources.arxiv import fetch_recent_papers
from sources.semantic_scholar import enrich_papers as enrich_semantic_scholar
from sources.openalex import enrich_papers as enrich_openalex
from sources.altmetric import enrich_papers as enrich_altmetric
from scoring import score_papers
from summarizer import summarize_papers
from leaderboard import fetch_candidate_pool, rank_foundations, rank_momentum
from ingest import (
    push_papers, push_metrics, push_summaries, push_digest, push_leaderboard,
    log_pipeline_start, log_pipeline_complete
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger('pipeline')


async def run_pipeline():
    today = date.today().isoformat()
    stats = {'date': today, 'papers_fetched': 0, 'papers_scored': 0, 'papers_summarized': 0}
    run_id = 0
    error_msg = None

    try:
        # Step 1: Log start
        logger.info('=== Research Papers Pipeline Starting ===')
        run_id = await log_pipeline_start()
        logger.info(f'Pipeline run ID: {run_id}')

        # Step 2: Fetch from arXiv
        logger.info(f'Step 1/7: Fetching arXiv papers (last {ARXIV_LOOKBACK_HOURS}h)')
        papers = await fetch_recent_papers(lookback_hours=ARXIV_LOOKBACK_HOURS)
        stats['papers_fetched'] = len(papers)
        logger.info(f'Fetched {len(papers)} unique papers')

        if not papers:
            logger.warning('No papers fetched — aborting pipeline')
            await log_pipeline_complete(run_id, stats, status='success')
            return

        # Step 3: Enrich with Semantic Scholar
        logger.info('Step 2/7: Enriching with Semantic Scholar')
        papers = await enrich_semantic_scholar(papers)

        # Step 4: Enrich with OpenAlex
        logger.info('Step 3/7: Enriching with OpenAlex')
        papers = await enrich_openalex(papers)

        # Step 5: Enrich with Altmetric
        logger.info('Step 4/7: Enriching with Altmetric')
        papers = await enrich_altmetric(papers)

        # Step 6: Score papers
        logger.info('Step 5/7: Computing composite scores')
        papers = score_papers(papers)
        stats['papers_scored'] = len(papers)
        if papers:
            top3 = papers[:3]
            for p in top3:
                logger.info(f'  Top paper: {p["composite_score"]:.4f} — {p["title"][:60]}')

        # Step 7: Push papers + metrics
        logger.info('Step 6/7: Pushing papers and metrics to Worker')
        inserted_papers = await push_papers(papers)
        inserted_metrics = await push_metrics(papers)
        logger.info(f'Inserted {inserted_papers} papers, {inserted_metrics} metrics records')

        # Step 8: Generate summaries for top N
        top_papers = papers[:DAILY_TOP_N]
        logger.info(f'Step 7/7: Summarizing top {len(top_papers)} papers')
        summaries = await summarize_papers(top_papers)
        stats['papers_summarized'] = len(summaries)

        # Step 9: Push summaries + digest
        if summaries:
            inserted_summaries = await push_summaries(summaries)
            logger.info(f'Inserted {inserted_summaries} summaries')

        inserted_digest = await push_digest(today, top_papers)
        logger.info(f'Created daily digest for {today} with {inserted_digest} entries')

        # Step 10: Log completion
        await log_pipeline_complete(run_id, stats, status='success')
        logger.info(f'=== Pipeline Complete: {stats} ===')

        # Step 11: Leaderboard (runs after main pipeline; non-blocking on failure)
        logger.info('Running leaderboard update...')
        try:
            await run_leaderboard()
        except Exception as lb_err:
            logger.error(f'Leaderboard step failed (non-fatal): {lb_err}')

    except Exception as e:
        error_msg = str(e)
        logger.error(f'Pipeline failed: {e}', exc_info=True)
        try:
            await log_pipeline_complete(run_id, stats, status='failed', error=error_msg)
        except Exception:
            pass
        sys.exit(1)


async def run_leaderboard():
    """Fetch candidate pool and produce both Foundations and Momentum leaderboards."""
    today = date.today().isoformat()
    logger.info('=== Leaderboard Pipeline Starting ===')

    try:
        # Step 1: fetch candidate pool (large, unranked)
        logger.info('Fetching leaderboard candidate pool from OpenAlex')
        pool = await fetch_candidate_pool()
        if not pool:
            logger.warning('Empty candidate pool — aborting leaderboard')
            return

        # Step 2: rank two ways
        foundations = rank_foundations(pool, limit=LEADERBOARD_SIZE)
        momentum = rank_momentum(pool, limit=LEADERBOARD_SIZE)
        logger.info(f'Ranked: {len(foundations)} foundations, {len(momentum)} momentum')

        # Log sample top entries for each list
        if foundations:
            top = foundations[0]
            logger.info(f'  Foundations #1: {top["citation_count"]} cites — {top["title"][:60]}')
        if momentum:
            top = momentum[0]
            logger.info(f'  Momentum #1: score={top.get("momentum_score", 0):.3f} — {top["title"][:60]}')

        # Step 3: union of all papers to upsert (foundations ∪ momentum, deduped)
        seen_ids: set[str] = set()
        all_papers: list[dict] = []
        for p in foundations + momentum:
            pid = p.get('id')
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(p)

        inserted_papers = await push_papers(all_papers)
        logger.info(f'Upserted {inserted_papers} leaderboard papers')

        inserted_metrics = await push_metrics(all_papers)
        logger.info(f'Pushed {inserted_metrics} metric records')

        # Step 4: summarize (only papers with abstracts)
        to_summarize = [p for p in all_papers if p.get('abstract')]
        if to_summarize:
            logger.info(f'Summarizing {len(to_summarize)} leaderboard papers with Claude')
            summaries = await summarize_papers(to_summarize)
            if summaries:
                inserted_summaries = await push_summaries(summaries)
                logger.info(f'Pushed {inserted_summaries} leaderboard summaries')

        # Step 5: push both snapshots
        inserted_f = await push_leaderboard(today, 'foundations', foundations)
        logger.info(f'Foundations snapshot for {today}: {inserted_f} entries')

        inserted_m = await push_leaderboard(today, 'momentum', momentum)
        logger.info(f'Momentum snapshot for {today}: {inserted_m} entries')

        logger.info('=== Leaderboard Pipeline Complete ===')

    except Exception as e:
        logger.error(f'Leaderboard pipeline failed: {e}', exc_info=True)


if __name__ == '__main__':
    if '--leaderboard-only' in sys.argv:
        asyncio.run(run_leaderboard())
    else:
        asyncio.run(run_pipeline())
