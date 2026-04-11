/**
 * Leaderboard pages — two variants:
 *   foundations: most-cited papers of all time (bedrock literature)
 *   momentum:    foundational papers still accelerating (landmark + trending)
 */

import { fetchLeaderboard } from './api.js';
import { tagPill, diffBadge, catBadge, pdfLink, fmtDate, escapeHtml, renderLatex } from './components.js';

const LIST_META = {
    foundations: {
        title: 'Most Cited',
        subtitle: 'Highest all-time citation counts · the bedrock literature every field builds on',
    },
    momentum: {
        title: 'Acceleration',
        subtitle: `Papers whose citation rate is accelerating \u00B7 second-derivative signal for what\u2019s rising fastest`,
    },
};

export function initLeaderboard(app, router, listType = 'foundations') {
    const meta = LIST_META[listType] || LIST_META.foundations;

    let state = {
        papers: [],
        loading: false,
    };

    function render() {
        app.innerHTML = `
            <div class="page-header">
                <span class="page-title">${meta.title}</span>
                <span style="font-size:10px;color:var(--text3);align-self:center">${meta.subtitle}</span>
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
                <strong>No data yet for ${meta.title}</strong>
                The pipeline needs to run the leaderboard flow to populate this list.
            </div>`;
        }

        const rows = papers.map((p, i) => paperRow(p, p.rank || i + 1));
        return `<div class="paper-list">${rows.join('')}</div>
            <div style="margin-top:12px;font-size:10px;color:var(--text3)">${papers.length} papers</div>`;
    }

    function paperRow(p, rank) {
        const tags = (p.tags || []).slice(0, 3).map(tagPill).join('');
        const citationLabel = p.citation_count != null
            ? `<span style="font-size:10px;color:var(--text3)">${p.citation_count.toLocaleString()} citations</span>`
            : '';
        const scoreLabel = listType === 'momentum' && p.score != null
            ? `<span style="font-size:10px;color:var(--gold);font-weight:700">accel ${p.score.toFixed(2)}</span>`
            : '';
        return `
            <div class="paper-row" data-id="${escapeHtml(p.id)}" role="button" tabindex="0">
                <div class="paper-rank">${rank}</div>
                <div class="paper-body">
                    <div class="paper-title">${escapeHtml(p.title)}</div>
                    ${p.tldr ? `<div class="paper-tldr">${escapeHtml(p.tldr)}</div>` : ''}
                    <div class="paper-footer">
                        ${scoreLabel}
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
            const data = await fetchLeaderboard(listType, 50);
            state.papers = data.papers || [];
        } catch (err) {
            console.error(`${meta.title} load error:`, err);
            state.papers = [];
        }

        state.loading = false;
        render();
    }

    load();
}
