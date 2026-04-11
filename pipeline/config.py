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
WEIGHT_CITATION_VEL: float = float(os.environ.get('WEIGHT_CITATION_VEL', '0.35'))
WEIGHT_ALTMETRIC: float = float(os.environ.get('WEIGHT_ALTMETRIC', '0.35'))
WEIGHT_AUTHOR_REP: float = float(os.environ.get('WEIGHT_AUTHOR_REP', '0.30'))
HALF_LIFE_DAYS: int = int(os.environ.get('HALF_LIFE_DAYS', '180'))

# Pipeline settings
DAILY_TOP_N: int = int(os.environ.get('DAILY_TOP_N', '30'))
ARXIV_LOOKBACK_HOURS: int = int(os.environ.get('ARXIV_LOOKBACK_HOURS', '48'))
SEED_LOOKBACK_DAYS: int = int(os.environ.get('SEED_LOOKBACK_DAYS', '30'))

# Leaderboard settings
LEADERBOARD_SIZE: int = int(os.environ.get('LEADERBOARD_SIZE', '50'))
# OpenAlex concept IDs to cover the same domains as arXiv categories
LEADERBOARD_CONCEPTS: list[str] = [
    # Broad fields
    'C154945302',  # Artificial intelligence
    'C119857082',  # Machine learning
    'C41008148',   # Computer science
    'C55493867',   # Biology
    'C121332964',  # Physics
    'C33923547',   # Mathematics
    'C162324750',  # Economics / Finance
    'C71924100',   # Medicine
    'C138496267',  # Statistics
    # ML sub-fields where landmark papers concentrate
    'C108583219',  # Deep learning
    'C50644808',   # Artificial neural network
    'C31972630',   # Computer vision
    'C204321447',  # Natural language processing
    # Chemistry — home of Lowry, Bradford, other high-citation bio-methods
    'C185592680',  # Chemistry
]

# Claude model for summarization
CLAUDE_MODEL: str = 'claude-sonnet-4-20250514'

# Tag categories for Claude to assign
SUMMARY_TAGS: list[str] = [
    'finance', 'policy', 'governance', 'energy', 'healthcare', 'defense',
    'climate', 'materials', 'AI/ML', 'biotech', 'quantitative-methods',
    'infrastructure', 'agriculture', 'space', 'neuroscience', 'drug-discovery'
]
