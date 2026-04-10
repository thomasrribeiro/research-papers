/**
 * Trends page
 */

import { fetchTrends } from './api.js';
import { escapeHtml, fmtDate } from './components.js';

export async function initTrends(app, router) {
    app.innerHTML = '<div class="loading-spinner">Loading trends...</div>';

    let data7, data30;
    try {
        [data7, data30] = await Promise.all([fetchTrends('7d'), fetchTrends('30d')]);
    } catch (err) {
        app.innerHTML = `<div class="empty-state"><strong>Failed to load trends</strong>${escapeHtml(err.message)}</div>`;
        return;
    }

    app.innerHTML = `
        <div class="page-header">
            <span class="page-title">Trends</span>
        </div>

        <div class="trends-grid">
            <!-- Top categories (7d) -->
            <div class="trends-card">
                <div class="trends-card-title">Top Fields — 7 Days</div>
                ${renderCategories(data7.categories)}
            </div>

            <!-- Rising stars -->
            <div class="trends-card">
                <div class="trends-card-title">Rising Stars (citation velocity)</div>
                ${renderRising(data7.rising_stars, router)}
            </div>

            <!-- Top categories (30d) -->
            <div class="trends-card">
                <div class="trends-card-title">Top Fields — 30 Days</div>
                ${renderCategories(data30.categories)}
            </div>

            <!-- Top papers (7d) -->
            <div class="trends-card">
                <div class="trends-card-title">Highest Scored — 7 Days</div>
                ${renderTopPapers(data7.top_papers)}
            </div>
        </div>
    `;

    // Paper row clicks
    app.querySelectorAll('.rising-item[data-id], .top-paper-row[data-id]').forEach(el => {
        el.addEventListener('click', () => router.navigate(`/paper/${el.dataset.id}`));
    });
}

function renderCategories(categories) {
    if (!categories || !categories.length) return '<div style="color:var(--text3);font-size:11px">No data yet</div>';
    return categories.map(c => `
        <div class="trend-cat-row">
            <span class="trend-cat-name">${escapeHtml(c.category)}</span>
            <span class="trend-cat-count">${c.paper_count} papers</span>
            <span class="trend-cat-score">${Math.round((c.avg_score || 0) * 100)}</span>
        </div>
    `).join('');
}

function renderRising(papers, router) {
    if (!papers || !papers.length) return '<div style="color:var(--text3);font-size:11px">No data yet</div>';
    return papers.map(p => `
        <div class="rising-item" data-id="${escapeHtml(p.id)}" role="button" tabindex="0">
            <div class="rising-title">${escapeHtml(p.title)}</div>
            <div class="rising-vel">${(p.citation_velocity || 0).toFixed(1)} cit/mo · ${fmtDate(p.published_date)}</div>
        </div>
    `).join('');
}

function renderTopPapers(papers) {
    if (!papers || !papers.length) return '<div style="color:var(--text3);font-size:11px">No data yet</div>';
    return papers.map((p, i) => `
        <div class="trend-cat-row top-paper-row" data-id="${escapeHtml(p.id)}" role="button" tabindex="0" style="cursor:pointer">
            <span class="trend-cat-name" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block">${i + 1}. ${escapeHtml(p.title)}</span>
            <span class="trend-cat-count">${escapeHtml(p.primary_category)}</span>
            <span class="trend-cat-score">${Math.round((p.composite_score || 0) * 100)}</span>
        </div>
    `).join('');
}
