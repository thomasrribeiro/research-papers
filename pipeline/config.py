"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field

# arXiv categories to monitor
ARXIV_CATEGORIES: list[str] = os.environ.get(
    'ARXIV_CATEGORIES',
    'cs.AI,cs.LG,cs.CL,q-bio.NC,q-bio.QM,physics.comp-ph,physics.data-an,'
    'math.OC,math.PR,math.ST,cond-mat.mtrl-sci,q-fin.PM,q-fin.ST,q-fin.TR,'
    'eess.SP,stat.ML,nlin.AO'
).split(',')

# API keys
ANTHROPIC_API_KEY: str = os.environ.get('ANTHROPIC_API_KEY', '')
SEMANTIC_SCHOLAR_API_KEY: str = os.environ.get('SEMANTIC_SCHOLAR_API_KEY', '')
OPENALEX_EMAIL: str = os.environ.get('OPENALEX_EMAIL', 'research-papers@thomasrribeiro.com')

# Worker API
WORKER_URL: str = os.environ.get('WORKER_URL', 'http://localhost:8787').rstrip('/')
PIPELINE_API_KEY: str = os.environ.get('PIPELINE_API_KEY', 'dev-pipeline-key')

# Scoring weights (must sum to 1.0)
WEIGHT_CITATION_VEL: float = float(os.environ.get('WEIGHT_CITATION_VEL', '0.25'))
WEIGHT_ALTMETRIC: float = float(os.environ.get('WEIGHT_ALTMETRIC', '0.25'))
WEIGHT_BRIDGE: float = float(os.environ.get('WEIGHT_BRIDGE', '0.30'))
WEIGHT_AUTHOR_REP: float = float(os.environ.get('WEIGHT_AUTHOR_REP', '0.20'))
HALF_LIFE_DAYS: int = int(os.environ.get('HALF_LIFE_DAYS', '180'))

# Pipeline settings
DAILY_TOP_N: int = int(os.environ.get('DAILY_TOP_N', '30'))
ARXIV_LOOKBACK_HOURS: int = int(os.environ.get('ARXIV_LOOKBACK_HOURS', '48'))
SEED_LOOKBACK_DAYS: int = int(os.environ.get('SEED_LOOKBACK_DAYS', '30'))

# Claude model for summarization
CLAUDE_MODEL: str = 'claude-sonnet-4-20250514'

# Domain classification for bridge score
STEM_DOMAINS: set[str] = {
    'Physics', 'Mathematics', 'Computer Science', 'Biology',
    'Chemistry', 'Engineering', 'Materials Science', 'Environmental Science'
}
APPLIED_DOMAINS: set[str] = {
    'Economics', 'Political Science', 'Business', 'Sociology',
    'Medicine', 'Finance', 'Public Health', 'Geography',
    'Law', 'History', 'Philosophy'
}

# Tag categories for Claude to assign
SUMMARY_TAGS: list[str] = [
    'finance', 'policy', 'governance', 'energy', 'healthcare', 'defense',
    'climate', 'materials', 'AI/ML', 'biotech', 'quantitative-methods',
    'infrastructure', 'agriculture', 'space', 'neuroscience', 'drug-discovery'
]
