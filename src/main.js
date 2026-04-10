/**
 * Entry point + hash-based router
 * Routes: #/ (feed), #/paper/:id (detail), #/trends, #/settings
 */

import { fetchStats, fetchCategories } from './api.js';
import { initFeed } from './feed.js';
import { initLeaderboard } from './leaderboard.js';
import { initPaperDetail } from './paper-detail.js';
import { initTrends } from './trends.js';
import { initSettings } from './settings.js';

const app = document.getElementById('app');

// Router state shared across pages
const router = {
    state: { availableDates: [], history: [] },
    navigate(hash) {
        this.state.history.push(location.hash);
        location.hash = hash;
    },
    back() {
        const prev = this.state.history.pop();
        if (prev) { location.hash = prev; }
        else { location.hash = '/'; }
    }
};

async function loadSidebar() {
    try {
        const stats = await fetchStats();

        // Stats
        const statTotal = document.getElementById('stat-total');
        const statToday = document.getElementById('stat-today');
        if (statTotal) statTotal.textContent = stats.total_papers?.toLocaleString() ?? '—';
        if (statToday) statToday.textContent = stats.today_ranked ?? '—';

        // Available dates for feed navigation
        if (stats.available_dates?.length) {
            router.state.availableDates = stats.available_dates;
        }

        // Pipeline status
        const indicator = document.getElementById('status-indicator');
        const statusText = document.getElementById('status-text');
        const statusDetail = document.getElementById('status-detail');
        const run = stats.last_pipeline_run;

        if (run) {
            const isOk = run.status === 'success';
            if (indicator) {
                indicator.className = `status-dot ${isOk ? 'ok' : 'err'}`;
            }
            if (statusText) statusText.textContent = run.status;
            if (statusDetail) {
                const when = run.completed_at ? new Date(run.completed_at).toLocaleDateString() : '—';
                statusDetail.textContent = `${when} · ${run.papers_fetched ?? 0} papers`;
            }
        } else {
            if (indicator) indicator.className = 'status-dot';
            if (statusText) statusText.textContent = 'never run';
        }

        // Category filter
        const catList = document.getElementById('category-list');
        if (catList) {
            try {
                const catData = await fetchCategories();
                const top10 = (catData.categories || []).slice(0, 10);
                catList.innerHTML = top10.map(c => `
                    <div class="cat-item">
                        <input type="checkbox" checked data-cat="${c.primary_category}">
                        <span>${c.primary_category} <span style="color:var(--text3)">(${c.count})</span></span>
                    </div>
                `).join('');
            } catch { /* non-critical */ }
        }
    } catch (err) {
        console.warn('Sidebar stats failed:', err.message);
        const statusText = document.getElementById('status-text');
        if (statusText) statusText.textContent = 'offline';
    }
}

function getRoute() {
    const hash = location.hash.replace(/^#/, '') || '/';
    const paperMatch = hash.match(/^\/paper\/(.+)$/);
    if (paperMatch) return { name: 'paper', id: paperMatch[1] };
    if (hash === '/trends') return { name: 'trends' };
    if (hash === '/settings') return { name: 'settings' };
    if (hash === '/leaderboard') return { name: 'leaderboard' };
    return { name: 'feed' };
}

function updateNavActive(routeName) {
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.route === routeName);
    });

    // Show/hide category filter (feed only)
    const catFilter = document.getElementById('category-filter');
    if (catFilter) catFilter.style.display = routeName === 'feed' ? '' : 'none';
}

async function route() {
    const r = getRoute();
    updateNavActive(r.name);

    switch (r.name) {
        case 'paper':
            await initPaperDetail(app, router, r.id);
            break;
        case 'trends':
            await initTrends(app, router);
            break;
        case 'settings':
            initSettings(app);
            break;
        case 'leaderboard':
            initLeaderboard(app, router);
            break;
        default:
            initFeed(app, router);
    }
}

// Theme toggle
function initTheme() {
    const saved = localStorage.getItem('rp_theme') || 'light';
    document.documentElement.dataset.theme = saved;

    document.getElementById('theme-toggle')?.addEventListener('click', () => {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        localStorage.setItem('rp_theme', next);
    });
}

// Init
window.addEventListener('hashchange', route);
initTheme();
loadSidebar();
route();
