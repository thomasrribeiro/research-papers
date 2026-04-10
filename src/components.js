/**
 * Shared UI components
 */

const TAG_CLASSES = {
    'finance': 'tag-finance',
    'policy': 'tag-policy',
    'governance': 'tag-governance',
    'energy': 'tag-energy',
    'healthcare': 'tag-healthcare',
    'defense': 'tag-defense',
    'climate': 'tag-climate',
    'materials': 'tag-materials',
    'AI/ML': 'tag-aiml',
    'biotech': 'tag-biotech',
    'quantitative-methods': 'tag-quantitative-methods',
    'infrastructure': 'tag-infrastructure',
    'agriculture': 'tag-agriculture',
    'space': 'tag-space',
    'neuroscience': 'tag-neuroscience',
    'drug-discovery': 'tag-drug-discovery',
};

export function tagPill(tag) {
    const cls = TAG_CLASSES[tag] || 'tag-default';
    return `<span class="tag-pill ${cls}">${escapeHtml(tag)}</span>`;
}

export function diffBadge(difficulty) {
    const d = Math.max(1, Math.min(5, difficulty || 3));
    const labels = { 1: 'accessible', 2: 'general', 3: 'technical', 4: 'advanced', 5: 'specialist' };
    return `<span class="diff-badge diff-${d}">${labels[d]}</span>`;
}

export function scoreBadge(score) {
    const pct = Math.round((score || 0) * 100);
    return `<span class="score-badge">${pct}</span>`;
}

export function catBadge(cat) {
    return `<span class="cat-badge">${escapeHtml(cat || '')}</span>`;
}

export function factorBars(breakdown) {
    if (!breakdown) return '';
    const factors = [
        { key: 'citation_vel', label: 'cit' },
        { key: 'altmetric', label: 'alt' },
        { key: 'bridge', label: 'bridge' },
        { key: 'author_rep', label: 'rep' },
    ];
    const bars = factors.map(f => {
        const val = breakdown[f.key] || 0;
        const h = Math.max(3, Math.round(val * 16));
        const opacity = 0.4 + val * 0.6;
        return `<div class="factor-bar" title="${f.label}: ${(val * 100).toFixed(0)}%" style="height:${h}px;opacity:${opacity.toFixed(2)};"></div>`;
    });
    return `<div class="factor-bars" title="score factors">${bars.join('')}</div>`;
}

export function scoreBreakdown(breakdown) {
    if (!breakdown) return '';
    const factors = [
        { key: 'citation_vel', label: 'Citation velocity' },
        { key: 'altmetric', label: 'Social attention' },
        { key: 'bridge', label: 'Cross-domain' },
        { key: 'author_rep', label: 'Author reputation' },
        { key: 'time_decay', label: 'Recency' },
    ];
    const rows = factors.map(f => {
        const val = breakdown[f.key] || 0;
        const pct = Math.round(val * 100);
        return `<div class="score-factor-row">
            <span class="score-factor-name">${f.label}</span>
            <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%"></div></div>
            <span class="score-factor-val">${pct}</span>
        </div>`;
    });
    return `<div class="score-breakdown">${rows.join('')}</div>`;
}

export function pdfLink(url, text = 'PDF') {
    if (!url) return '';
    return `<a href="${url}" target="_blank" rel="noopener" class="pdf-link" onclick="event.stopPropagation()">${text}</a>`;
}

/** Format YYYY-MM-DD to human-readable */
export function fmtDate(dateStr) {
    if (!dateStr) return '';
    try {
        return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric'
        });
    } catch {
        return dateStr;
    }
}

export function escapeHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function renderLatex(container) {
    if (window.renderMathInElement) {
        window.renderMathInElement(container, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false }
            ],
            throwOnError: false
        });
    }
}
