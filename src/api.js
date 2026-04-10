/**
 * Worker API client
 */

const WORKER_URL = (import.meta.env.VITE_WORKER_URL || 'http://localhost:8787').replace(/\/$/, '');

async function get(path) {
    const resp = await fetch(`${WORKER_URL}${path}`);
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${path}`);
    return resp.json();
}

export function fetchPapers({ date, category, limit = 50, offset = 0, sort = 'composite', tag, minScore = 0 } = {}) {
    const params = new URLSearchParams();
    if (date) params.set('date', date);
    if (category) params.set('category', category);
    params.set('limit', limit);
    params.set('offset', offset);
    params.set('sort', sort);
    if (tag) params.set('tag', tag);
    if (minScore > 0) params.set('min_score', minScore);
    return get(`/api/papers?${params}`);
}

export function fetchPaper(id) {
    return get(`/api/papers/${encodeURIComponent(id)}`);
}

export function searchPapers(q, limit = 20) {
    return get(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export function fetchTrends(period = '7d') {
    return get(`/api/trends?period=${period}`);
}

export function fetchCategories() {
    return get('/api/categories');
}

export function fetchStats() {
    return get('/api/stats');
}
