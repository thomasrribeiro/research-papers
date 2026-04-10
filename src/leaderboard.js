/**
 * Leaderboard page — top-cited papers of all time
 */

import { fetchLeaderboard } from './api.js';
import { tagPill, diffBadge, scoreBadge, catBadge, factorBars, pdfLink, fmtDate, escapeHtml, renderLatex } from './components.js';

export function initLeaderboard(app, router) {
    let state = {
        papers: [],
        loading: false,
    };

    function render() {
        app.innerHTML = `
            <div class="page-header">
                <span class="page-title">Leaderboard</span>
                <span style="font-size:10px;color:var(--text3);align-self:center">Top-cited papers of all time · updates daily</span>
            </div>

            ${state.loading
                ? '<div class="loading-spinner">Loading papers...</div>'
                : renderPaperList(state.papers)
            }
        `;

        bindEvents();
        renderLatex(app);
    }

    function renderPaperList(papers) {
        if (!papers.length) {
            return `<div class="empty-state">
                <strong>No leaderboard data yet</strong>
                The pipeline needs to run with the leaderboard flow to populate this list.
            </div>`;
        }

        const rows = papers.map((p, i) => paperRow(p, p.rank || i + 1));
        return `<div class="paper-list">${rows.join('')}</div>
            <div style="margin-top:12px;font-size:10px;color:var(--text3)">${papers.length} high-impact papers</div>`;
    }

    function paperRow(p, rank) {
        const tags = (p.tags || []).slice(0, 3).map(tagPill).join('');
        const citationLabel = p.citation_count != null
            ? `<span style="font-size:10px;color:var(--text3)">${p.citation_count.toLocaleString()} citations</span>`
            : '';
        return `
            <div class="paper-row" data-id="${escapeHtml(p.id)}" role="button" tabindex="0">
                <div class="paper-rank">${rank}</div>
                <div class="paper-body">
                    <div class="paper-title">${escapeHtml(p.title)}</div>
                    ${p.tldr ? `<div class="paper-tldr">${escapeHtml(p.tldr)}</div>` : ''}
                    <div class="paper-footer">
                        ${citationLabel}
                        ${catBadge(p.primary_category)}
                        ${p.published_date ? `<span style="font-size:10px;color:var(--text3)">${fmtDate(p.published_date)}</span>` : ''}
                        ${p.difficulty ? diffBadge(p.difficulty) : ''}
                        ${tags}
                        ${pdfLink(p.pdf_url)}
                    </div>
                </div>
            </div>
        `;
    }

    function bindEvents() {
        app.querySelectorAll('.paper-row').forEach(row => {
            row.addEventListener('click', () => {
                router.navigate(`/paper/${row.dataset.id}`);
            });
            row.addEventListener('keydown', e => {
                if (e.key === 'Enter') router.navigate(`/paper/${row.dataset.id}`);
            });
        });
    }

    async function load() {
        state.loading = true;
        render();

        try {
            const data = await fetchLeaderboard(50);
            state.papers = data.papers || [];
        } catch (err) {
            console.error('Leaderboard load error:', err);
            state.papers = [];
        }

        state.loading = false;
        render();
    }

    load();
}
