/**
 * Daily Feed page — ranked list of today's top papers
 */

import { fetchPapers, searchPapers } from './api.js';
import { tagPill, diffBadge, scoreBadge, catBadge, factorBars, pdfLink, fmtDate, escapeHtml, renderLatex } from './components.js';

const SORT_OPTIONS = [
    { value: 'composite', label: 'Score' },
    { value: 'recency', label: 'Recency' },
    { value: 'citations', label: 'Citations' },
    { value: 'altmetric', label: 'Social' },
];

export function initFeed(app, router) {
    let state = {
        date: todayISO(),
        sort: 'composite',
        tag: '',
        minScore: 0,
        search: '',
        papers: [],
        total: 0,
        loading: false,
        availableDates: router.state?.availableDates || [],
    };

    function render() {
        app.innerHTML = `
            <div class="page-header">
                <span class="page-title">Daily Feed</span>
                <div class="date-nav">
                    <button id="prev-date" ${!canGoPrev() ? 'disabled' : ''}>←</button>
                    <span class="date-label">${fmtDate(state.date)}</span>
                    <button id="next-date" ${!canGoNext() ? 'disabled' : ''}>→</button>
                </div>
            </div>

            <div class="feed-controls">
                <input type="text" id="search-input" placeholder="Search papers..." value="${escapeHtml(state.search)}">
                <select class="control-select" id="sort-select">
                    ${SORT_OPTIONS.map(o => `<option value="${o.value}" ${state.sort === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                </select>
                <select class="control-select" id="tag-select">
                    <option value="">All tags</option>
                    ${getTagOptions().map(t => `<option value="${t}" ${state.tag === t ? 'selected' : ''}>${t}</option>`).join('')}
                </select>
                <select class="control-select" id="score-select">
                    <option value="0" ${state.minScore === 0 ? 'selected' : ''}>Any score</option>
                    <option value="0.3" ${state.minScore === 0.3 ? 'selected' : ''}>> 30</option>
                    <option value="0.5" ${state.minScore === 0.5 ? 'selected' : ''}>> 50</option>
                    <option value="0.7" ${state.minScore === 0.7 ? 'selected' : ''}>> 70</option>
                </select>
            </div>

            ${state.loading
                ? '<div class="loading-spinner">Loading papers...</div>'
                : renderPaperList(state.papers, state.total, state.date, state.search)
            }
        `;

        bindEvents();
        renderLatex(app);
    }

    function renderPaperList(papers, total, date, search) {
        if (!papers.length) {
            return `<div class="empty-state">
                <strong>${search ? 'No results' : 'No papers yet'}</strong>
                ${search ? `No papers matching "${escapeHtml(search)}"` : `No data for ${fmtDate(date)}. The pipeline may not have run yet.`}
            </div>`;
        }

        const rows = papers.map((p, i) => paperRow(p, p.rank || i + 1));
        return `<div class="paper-list">${rows.join('')}</div>
            <div style="margin-top:12px;font-size:10px;color:var(--text3)">${total} papers${search ? ` matching "${escapeHtml(search)}"` : ''}</div>`;
    }

    function paperRow(p, rank) {
        const tags = (p.tags || []).slice(0, 3).map(tagPill).join('');
        return `
            <div class="paper-row" data-id="${escapeHtml(p.id)}" role="button" tabindex="0">
                <div class="paper-rank">${rank}</div>
                <div class="paper-body">
                    <div class="paper-title">${escapeHtml(p.title)}</div>
                    ${p.tldr ? `<div class="paper-tldr">${escapeHtml(p.tldr)}</div>` : ''}
                    <div class="paper-footer">
                        ${scoreBadge(p.composite_score)}
                        ${factorBars(p.factor_breakdown)}
                        ${catBadge(p.primary_category)}
                        ${p.difficulty ? diffBadge(p.difficulty) : ''}
                        ${tags}
                        ${pdfLink(p.pdf_url)}
                    </div>
                </div>
            </div>
        `;
    }

    function bindEvents() {
        // Row click → detail
        app.querySelectorAll('.paper-row').forEach(row => {
            row.addEventListener('click', () => {
                router.navigate(`/paper/${row.dataset.id}`);
            });
            row.addEventListener('keydown', e => {
                if (e.key === 'Enter') router.navigate(`/paper/${row.dataset.id}`);
            });
        });

        // Date nav
        app.querySelector('#prev-date')?.addEventListener('click', () => navigateDate(-1));
        app.querySelector('#next-date')?.addEventListener('click', () => navigateDate(1));

        // Sort
        app.querySelector('#sort-select')?.addEventListener('change', e => {
            state.sort = e.target.value;
            load();
        });

        // Tag filter
        app.querySelector('#tag-select')?.addEventListener('change', e => {
            state.tag = e.target.value;
            load();
        });

        // Score filter
        app.querySelector('#score-select')?.addEventListener('change', e => {
            state.minScore = parseFloat(e.target.value);
            load();
        });

        // Search (debounced)
        let searchTimer;
        app.querySelector('#search-input')?.addEventListener('input', e => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                state.search = e.target.value.trim();
                load();
            }, 350);
        });
    }

    function navigateDate(dir) {
        const dates = state.availableDates;
        if (!dates.length) return;
        const idx = dates.indexOf(state.date);
        const newIdx = idx === -1 ? 0 : Math.max(0, Math.min(dates.length - 1, idx - dir));
        state.date = dates[newIdx];
        load();
    }

    function canGoPrev() {
        const dates = state.availableDates;
        if (!dates.length) return false;
        const idx = dates.indexOf(state.date);
        return idx < dates.length - 1;
    }

    function canGoNext() {
        const dates = state.availableDates;
        if (!dates.length) return false;
        const idx = dates.indexOf(state.date);
        return idx > 0;
    }

    async function load() {
        state.loading = true;
        render();

        try {
            let data;
            if (state.search) {
                data = await searchPapers(state.search, 50);
                state.papers = data.papers || [];
                state.total = state.papers.length;
            } else {
                data = await fetchPapers({
                    date: state.date,
                    sort: state.sort,
                    tag: state.tag || undefined,
                    minScore: state.minScore,
                    limit: 50
                });
                state.papers = data.papers || [];
                state.total = data.total || 0;

                // If today has no papers yet, silently fall back to the most recent
                // available date so the feed never shows empty after a pipeline run.
                const dates = router.state?.availableDates || [];
                if (!state.papers.length && dates.length && dates[0] !== state.date) {
                    state.date = dates[0];
                    data = await fetchPapers({
                        date: state.date,
                        sort: state.sort,
                        tag: state.tag || undefined,
                        minScore: state.minScore,
                        limit: 50
                    });
                    state.papers = data.papers || [];
                    state.total = data.total || 0;
                }
            }
        } catch (err) {
            console.error('Feed load error:', err);
            state.papers = [];
            state.total = 0;
        }

        state.loading = false;
        render();
    }

    load();
}

function todayISO() {
    // Use Pacific Time (America/Los_Angeles) — matches pipeline digest dates
    return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' });
}

function getTagOptions() {
    return [
        'AI/ML', 'finance', 'policy', 'governance', 'energy', 'healthcare',
        'defense', 'climate', 'materials', 'biotech', 'quantitative-methods',
        'infrastructure', 'agriculture', 'space', 'neuroscience', 'drug-discovery'
    ];
}
