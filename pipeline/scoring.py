"""
Multi-factor composite scoring engine.

Computes a score in [0, 1] for each paper based on:
  - Citation velocity (35%)
  - Altmetric attention (35%)
  - Author reputation via h-index (30%)

All factors are min-max normalized across the daily batch before weighting.
A time-decay factor is applied to the composite score.
"""

import math
import logging
from statistics import median

from config import (
    WEIGHT_CITATION_VEL, WEIGHT_ALTMETRIC, WEIGHT_AUTHOR_REP,
    HALF_LIFE_DAYS
)

logger = logging.getLogger(__name__)


def score_papers(papers: list[dict]) -> list[dict]:
    """
    Compute composite_score and factor_breakdown for each paper.
    Modifies papers in-place and returns sorted by composite_score descending.
    """
    if not papers:
        return papers

    # Raw factor vectors
    citation_vels = [p.get('citation_velocity', 0) or 0 for p in papers]
    altmetrics = [p.get('altmetric_score', 0) or 0 for p in papers]
    h_indices = [p.get('h_index_avg', 0) or 0 for p in papers]

    # Medians for graceful degradation (missing data → median, not 0)
    med_cv = median(citation_vels) if citation_vels else 0
    med_am = median(altmetrics) if altmetrics else 0
    med_hi = median(h_indices) if h_indices else 0

    # Replace zeros with medians only when no data was fetched at all
    # (i.e. when the value is exactly 0 AND we suspect API failure)
    # Strategy: if >80% of papers have 0 for a field, use median substitution
    cv_all_zero = sum(1 for v in citation_vels if v == 0) > 0.8 * len(papers)
    am_all_zero = sum(1 for v in altmetrics if v == 0) > 0.8 * len(papers)

    def effective(raw_val, all_zero, med):
        return med if (all_zero and raw_val == 0) else raw_val

    raw_cvs = [effective(v, cv_all_zero, med_cv) for v in citation_vels]
    raw_ams = [effective(v, am_all_zero, med_am) for v in altmetrics]

    # Min-max normalisation
    norm_cv = _minmax_normalize(raw_cvs)
    norm_am = _minmax_normalize(raw_ams)
    norm_hi = _minmax_normalize([p.get('h_index_avg', 0) or 0 for p in papers])

    from datetime import date as date_mod
    today = date_mod.today()

    for i, paper in enumerate(papers):
        # Time decay: newer papers score higher
        pub = paper.get('published_date', '')
        try:
            pub_date = date_mod.fromisoformat(pub)
            age_days = max(0, (today - pub_date).days)
        except (ValueError, TypeError):
            age_days = 0
        time_decay = math.exp(-0.693 * age_days / HALF_LIFE_DAYS)

        raw_composite = (
            WEIGHT_CITATION_VEL * norm_cv[i] +
            WEIGHT_ALTMETRIC * norm_am[i] +
            WEIGHT_AUTHOR_REP * norm_hi[i]
        )
        composite = raw_composite * time_decay

        paper['composite_score'] = round(composite, 6)
        paper['factor_breakdown'] = {
            'citation_vel': round(norm_cv[i], 4),
            'altmetric': round(norm_am[i], 4),
            'author_rep': round(norm_hi[i], 4),
            'time_decay': round(time_decay, 4)
        }

    papers.sort(key=lambda p: p['composite_score'], reverse=True)
    return papers



def _minmax_normalize(values: list[float]) -> list[float]:
    """Min-max normalize a list to [0, 1]. Returns 0.5 for constant inputs."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]
