/**
 * Settings page — scoring weights, category subscriptions
 */

import { escapeHtml } from './components.js';

const ARXIV_CATEGORIES = [
    'cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.RO',
    'q-bio.NC', 'q-bio.QM', 'q-bio.BM',
    'physics.comp-ph', 'physics.data-an', 'physics.med-ph',
    'math.OC', 'math.PR', 'math.ST',
    'cond-mat.mtrl-sci', 'cond-mat.soft',
    'q-fin.PM', 'q-fin.ST', 'q-fin.TR', 'q-fin.MF',
    'eess.SP', 'stat.ML', 'nlin.AO'
];

const DEFAULT_WEIGHTS = {
    citation_vel: 0.25,
    altmetric: 0.25,
    bridge: 0.30,
    author_rep: 0.20
};

const WEIGHT_LABELS = {
    citation_vel: 'Citation velocity',
    altmetric: 'Social attention',
    bridge: 'Cross-domain',
    author_rep: 'Author reputation'
};

export function initSettings(app) {
    let weights = loadWeights();
    let selectedCats = loadCategories();

    function render() {
        app.innerHTML = `
            <div class="page-header">
                <span class="page-title">Settings</span>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">Scoring Weights</div>
                <div id="weight-sliders">
                    ${Object.entries(weights).map(([key, val]) => `
                        <div class="weight-row">
                            <span class="weight-label">${WEIGHT_LABELS[key] || key}</span>
                            <input type="range" class="weight-slider" data-key="${key}"
                                min="0" max="1" step="0.05" value="${val}">
                            <span class="weight-val" id="wval-${key}">${Math.round(val * 100)}%</span>
                        </div>
                    `).join('')}
                </div>
                <div style="font-size:10px;color:var(--text3);margin-top:8px">
                    Total: <span id="weight-total">${totalPct(weights)}%</span>
                    ${Math.round(totalPct(weights)) !== 100 ? '<span style="color:#f44336"> (should sum to 100%)</span>' : ''}
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">arXiv Categories</div>
                <div class="cat-checkbox-grid">
                    ${ARXIV_CATEGORIES.map(cat => `
                        <label class="cat-checkbox-item">
                            <input type="checkbox" data-cat="${cat}" ${selectedCats.includes(cat) ? 'checked' : ''}>
                            ${escapeHtml(cat)}
                        </label>
                    `).join('')}
                </div>
            </div>

            <div class="settings-section">
                <div class="settings-section-title">Daily Digest Email</div>
                <div style="font-size:11px;color:var(--text3)">Coming soon — enter your email to receive a daily summary.</div>
                <input type="email" style="margin-top:8px;background:var(--bg2);border:1px solid var(--card-border);color:var(--text);font-family:inherit;font-size:12px;padding:6px 10px;border-radius:3px;outline:none;width:240px" placeholder="your@email.com" disabled>
            </div>

            <button class="settings-save-btn" id="save-btn">Save Settings</button>
            <div id="save-msg" style="margin-top:8px;font-size:11px;color:#4caf50;display:none">Settings saved.</div>
        `;

        // Weight sliders
        app.querySelectorAll('.weight-slider').forEach(slider => {
            slider.addEventListener('input', e => {
                const key = e.target.dataset.key;
                weights[key] = parseFloat(e.target.value);
                app.querySelector(`#wval-${key}`).textContent = Math.round(weights[key] * 100) + '%';
                app.querySelector('#weight-total').textContent = totalPct(weights) + '%';
            });
        });

        // Category checkboxes
        app.querySelectorAll('[data-cat]').forEach(cb => {
            cb.addEventListener('change', e => {
                const cat = e.target.dataset.cat;
                if (e.target.checked) {
                    if (!selectedCats.includes(cat)) selectedCats.push(cat);
                } else {
                    selectedCats = selectedCats.filter(c => c !== cat);
                }
            });
        });

        // Save
        app.querySelector('#save-btn').addEventListener('click', () => {
            saveWeights(weights);
            saveCategories(selectedCats);
            const msg = app.querySelector('#save-msg');
            msg.style.display = 'block';
            setTimeout(() => { msg.style.display = 'none'; }, 2000);
        });
    }

    render();
}

function totalPct(w) {
    return Math.round(Object.values(w).reduce((a, b) => a + b, 0) * 100);
}

function loadWeights() {
    try {
        const stored = localStorage.getItem('rp_weights');
        return stored ? { ...DEFAULT_WEIGHTS, ...JSON.parse(stored) } : { ...DEFAULT_WEIGHTS };
    } catch { return { ...DEFAULT_WEIGHTS }; }
}

function saveWeights(w) {
    localStorage.setItem('rp_weights', JSON.stringify(w));
}

function loadCategories() {
    try {
        const stored = localStorage.getItem('rp_categories');
        return stored ? JSON.parse(stored) : ARXIV_CATEGORIES.slice(0, 10);
    } catch { return ARXIV_CATEGORIES.slice(0, 10); }
}

function saveCategories(cats) {
    localStorage.setItem('rp_categories', JSON.stringify(cats));
}
