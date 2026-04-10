"""
Generate plain-language summaries and relevance tags for top papers
using the Claude API (claude-sonnet-4-20250514).
"""

import asyncio
import json
import logging
import re

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SUMMARY_TAGS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    'You are a research analyst who makes cutting-edge academic papers accessible. '
    'Given a paper title and abstract, you produce concise, accurate summaries '
    'for a STEM-educated generalist audience.'
)

USER_TEMPLATE = """Summarize this research paper.

Title: {title}

Abstract: {abstract}

Categories: {categories}

Produce a JSON response with exactly these keys:
- "tldr": A 2-3 sentence plain-language summary accessible to a STEM-educated generalist
- "so_what": A single sentence explaining why this matters beyond academia
- "tags": An array of applicable tags from this list only: {tags}
- "difficulty": An integer from 1 (broadly accessible) to 5 (requires deep specialist knowledge)

Return only valid JSON, no markdown fences."""


async def summarize_papers(papers: list[dict]) -> list[dict]:
    """
    Generate summaries for the given papers.
    Returns a list of summary dicts: {paper_id, tldr, so_what, tags, difficulty}.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning('ANTHROPIC_API_KEY not set — skipping summarization')
        return []

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    summaries = []
    tags_str = ', '.join(SUMMARY_TAGS)

    logger.info(f'Generating summaries for {len(papers)} papers')

    for paper in papers:
        arxiv_id = paper.get('arxiv_id') or paper.get('id')
        try:
            summary = await _summarize_one(client, paper, tags_str)
            if summary:
                summaries.append({'paper_id': arxiv_id, **summary})
                logger.debug(f'Summarized {arxiv_id}: {summary["tldr"][:60]}...')
        except anthropic.APIError as e:
            logger.warning(f'Claude API error for {arxiv_id}: {e}')
            if 'rate_limit' in str(e).lower() or 'overloaded' in str(e).lower():
                await asyncio.sleep(30)
        except Exception as e:
            logger.warning(f'Summarization error for {arxiv_id}: {e}')

        # Small delay between Claude calls
        await asyncio.sleep(0.5)

    logger.info(f'Generated {len(summaries)} summaries')
    return summaries


async def _summarize_one(
    client: anthropic.AsyncAnthropic,
    paper: dict,
    tags_str: str
) -> dict | None:
    """Call Claude for a single paper. Returns summary dict or None on failure."""
    categories = ', '.join(paper.get('categories', []) or [])
    prompt = USER_TEMPLATE.format(
        title=paper.get('title', ''),
        abstract=(paper.get('abstract', '') or '')[:2000],  # truncate very long abstracts
        categories=categories,
        tags=tags_str
    )

    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': prompt}]
    )

    text = response.content[0].text.strip()

    # Strip markdown code fences if Claude includes them
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f'JSON parse error: {e} — raw: {text[:200]}')
        return None

    # Validate and sanitize fields
    tldr = str(data.get('tldr', '')).strip()
    so_what = str(data.get('so_what', '')).strip()
    raw_tags = data.get('tags', [])
    valid_tags = [t for t in (raw_tags if isinstance(raw_tags, list) else []) if t in SUMMARY_TAGS]
    difficulty = int(data.get('difficulty', 3))
    difficulty = max(1, min(5, difficulty))

    if not tldr or not so_what:
        return None

    return {
        'tldr': tldr,
        'so_what': so_what,
        'tags': valid_tags,
        'difficulty': difficulty,
        'model': CLAUDE_MODEL
    }
