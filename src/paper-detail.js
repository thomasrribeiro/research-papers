/**
 * Paper Detail page
 */

import { fetchPaper } from './api.js';
import { tagPill, diffBadge, scoreBadge, catBadge, scoreBreakdown, metricsGrid, fmtDate, escapeHtml, stripHtml, renderLatex } from './components.js';

export async function initPaperDetail(app, router, paperId) {
    app.innerHTML = '<div class="loading-spinner">Loading paper...</div>';

    let paper;
    try {
        paper = await fetchPaper(paperId);
    } catch (err) {
        app.innerHTML = `<div class="empty-state"><strong>Paper not found</strong>${escapeHtml(err.message)}</div>`;
        return;
    }

    const authors = (paper.authors || []).slice(0, 8);
    const tags = (paper.tags || []).map(tagPill).join('');

    const semanticUrl = `https://api.semanticscholar.org/graph/v1/paper/ARXIV:${paper.arxiv_id}`;
    const arxivUrl = `https://arxiv.org/abs/${paper.arxiv_id}`;

    app.innerHTML = `
        <div class="detail-header">
            <div class="detail-back" id="back-btn">← Back to feed</div>
            <div class="detail-title">${escapeHtml(paper.title)}</div>
            <div class="detail-meta">
                ${scoreBadge(paper.composite_score)}
                ${catBadge(paper.primary_category)}
                ${paper.difficulty ? diffBadge(paper.difficulty) : ''}
                <span style="font-size:10px;color:var(--text3)">${fmtDate(paper.published_date)}</span>
                ${tags}
            </div>
            <div class="detail-links">
                ${paper.pdf_url ? `<a href="${escapeHtml(paper.pdf_url)}" target="_blank" rel="noopener" class="detail-link">PDF</a>` : ''}
                <a href="${escapeHtml(arxivUrl)}" target="_blank" rel="noopener" class="detail-link">arXiv</a>
                <a href="https://www.semanticscholar.org/search?q=${encodeURIComponent(paper.title)}" target="_blank" rel="noopener" class="detail-link">Semantic Scholar</a>
            </div>
        </div>

        ${paper.tldr ? `
        <div class="detail-section">
            <div class="detail-section-label">Summary</div>
            <div class="detail-tldr">${escapeHtml(paper.tldr)}</div>
            ${paper.so_what ? `<div class="detail-sowhat">${escapeHtml(paper.so_what)}</div>` : ''}
        </div>` : ''}

        <div class="detail-section">
            <div class="detail-section-label">Abstract</div>
            <div class="detail-abstract">${escapeHtml(stripHtml(paper.abstract))}</div>
        </div>

        <div class="detail-section">
            <div class="detail-section-label">${paper.factor_breakdown && Object.keys(paper.factor_breakdown).length ? 'Score Breakdown' : 'Paper Metrics'}</div>
            ${paper.factor_breakdown && Object.keys(paper.factor_breakdown).length ? scoreBreakdown(paper.factor_breakdown) : metricsGrid(paper)}
        </div>

        ${authors.length ? `
        <div class="detail-section">
            <div class="detail-section-label">Authors</div>
            <div class="author-list">
                ${authors.map(a => `
                    <div class="author-item">
                        ${escapeHtml(a.name || '')}
                        ${a.affiliation ? `<span style="color:var(--text3)"> · ${escapeHtml(a.affiliation)}</span>` : ''}
                    </div>
                `).join('')}
                ${paper.h_index_avg ? `<div style="margin-top:6px;font-size:10px;color:var(--text3)">avg. h-index: ${(paper.h_index_avg || 0).toFixed(1)}</div>` : ''}
            </div>
        </div>` : ''}

        ${(paper.fields_of_study || []).length || (paper.openalex_concepts || []).length ? `
        <div class="detail-section">
            <div class="detail-section-label">Fields</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px">
                ${[...(paper.fields_of_study || []), ...(paper.openalex_concepts || [])].map(f =>
                    `<span class="cat-badge">${escapeHtml(f)}</span>`
                ).join('')}
            </div>
        </div>` : ''}

        ${(paper.related || []).length ? `
        <div class="detail-section">
            <div class="detail-section-label">Related Papers</div>
            <div class="related-list">
                ${paper.related.map(r => `
                    <div class="related-item" data-id="${escapeHtml(r.id)}" role="button" tabindex="0">
                        <span class="related-title">${escapeHtml(r.title)}</span>
                        <span class="related-score">${Math.round((r.composite_score || 0) * 100)}</span>
                    </div>
                `).join('')}
            </div>
        </div>` : ''}
    `;

    renderLatex(app);

    // Back button
    app.querySelector('#back-btn')?.addEventListener('click', () => {
        router.back();
    });

    // Related paper clicks
    app.querySelectorAll('.related-item').forEach(el => {
        el.addEventListener('click', () => router.navigate(`/paper/${el.dataset.id}`));
        el.addEventListener('keydown', e => { if (e.key === 'Enter') router.navigate(`/paper/${el.dataset.id}`); });
    });
}
