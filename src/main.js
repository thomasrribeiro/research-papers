/**
 * Entry point + hash-based router
 * Routes: #/ (feed), #/paper/:id (detail), #/trends, #/settings
 */

import { fetchStats, fetchCategories, triggerPipeline } from './api.js';
import { initFeed } from './feed.js';
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
                        <input type="checkbox" checked data-cat="${c.category}">
                        <span>${c.category} <span style="color:var(--text3)">(${c.count})</span></span>
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
        default:
            initFeed(app, router);
    }
}

// Run Now button
function initRunNow() {
    const btn = document.getElementById('run-now-btn');
    const msg = document.getElementById('run-now-msg');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const key = localStorage.getItem('rp_pipeline_key');
        if (!key) {
            const entered = prompt('Enter your pipeline key (saved in Settings):');
            if (!entered) return;
            localStorage.setItem('rp_pipeline_key', entered);
        }

        btn.disabled = true;
        btn.textContent = 'Triggering...';
        msg.textContent = '';
        msg.className = 'run-now-msg';

        try {
            await triggerPipeline(localStorage.getItem('rp_pipeline_key'));
            msg.textContent = 'Pipeline started — check back in ~10 min.';
            msg.className = 'run-now-msg ok';
            btn.textContent = 'Triggered!';
            setTimeout(() => {
                btn.disabled = false;
                btn.textContent = 'Run now';
            }, 30000); // prevent double-triggering for 30s
        } catch (err) {
            msg.textContent = err.message.includes('401') ? 'Wrong key.' : err.message;
            msg.className = 'run-now-msg err';
            btn.disabled = false;
            btn.textContent = 'Run now';
            if (err.message.includes('401')) localStorage.removeItem('rp_pipeline_key');
        }
    });
}

// Theme toggle
function initTheme() {
    const saved = localStorage.getItem('rp_theme') || 'dark';
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
initRunNow();
loadSidebar();
route();
