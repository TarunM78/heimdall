/* =====================================================
   HEIMDALL – App Logic
   ===================================================== */

const API = '';

/* ---- State ---- */
let holdings = [];
let profile  = {};
let activeTab = 'brief';
let tabs = {}; // populated after DOM ready

/* ---- DOM ---- */
const $ = id => document.getElementById(id);

/* =====================================================
   TOOLTIPS for financial terms
   ===================================================== */
const TIPS = {
    'Sharpe Ratio':           "Measures return per unit of risk. Above 1.0 = good, above 2.0 = excellent. Below 0 means you'd be better off in cash.",
    'Annual Volatility':      'How much the portfolio swings year-to-year (std dev of daily returns x sqrt(252)). Higher = riskier.',
    'Annual Return (est.)':   'Estimated annualised return based on last 1 year of price data. Past performance does not guarantee future results.',
    'Portfolio Value':        'Sum of (current price x quantity) across all your holdings.',
    'Diversification Score':  'A 0-100 score based on number of holdings, sector spread, and single-name concentration. Higher is safer.',
    'P&L':                    'Profit & Loss: (current price - your avg cost) x quantity. Unrealised until you sell.',
    'Weight':                 'What percentage of your total portfolio value this position makes up.',
};


/* =====================================================
   INIT
   ===================================================== */
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize tabs AFTER DOM is ready
    tabs.brief     = { nav: $('nav-brief'),     panel: $('tab-brief') };
    tabs.analytics = { nav: $('nav-analytics'), panel: $('tab-analytics') };
    tabs.actions   = { nav: $('nav-actions'),   panel: $('tab-actions') };
    tabs.portfolio = { nav: $('nav-portfolio'), panel: $('tab-portfolio') };

    $('current-date').textContent = new Date().toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
    });
    await Promise.all([loadPortfolio(), loadProfile()]);
    setupNav();
    setupPortfolioForm();
    setupCSV();
    setupProfile();
    setupBrief();
    setupAnalytics();
    setupActions();
    setupSidebar();
});

/* =====================================================
   NAVIGATION
   ===================================================== */
function setupNav() {
    Object.entries(tabs).forEach(([key, { nav }]) => {
        nav.addEventListener('click', () => switchTab(key));
    });
}

function switchTab(key) {
    activeTab = key;
    Object.entries(tabs).forEach(([k, { nav, panel }]) => {
        const on = k === key;
        nav.classList.toggle('active', on);
        panel.classList.toggle('active', on);
    });
    const titleMap = { brief: 'Morning Brief', analytics: 'Analytics', actions: 'Action Items', portfolio: 'Portfolio' };
    $('page-title').textContent = titleMap[key] || key;
    $('sidebar').classList.remove('open');
}

/* =====================================================
   SIDEBAR (mobile)
   ===================================================== */
function setupSidebar() {
    $('hamburger').addEventListener('click', () => $('sidebar').classList.add('open'));
    $('sidebar-close').addEventListener('click', () => $('sidebar').classList.remove('open'));
}

/* =====================================================
   PORTFOLIO
   ===================================================== */
async function loadPortfolio() {
    try {
        const res  = await fetch(`${API}/api/portfolio`);
        const data = await res.json();
        holdings = data.holdings || [];
        renderHoldingsTable();
    } catch(e) { console.error('loadPortfolio', e); }
}

async function savePortfolio() {
    await fetch(`${API}/api/portfolio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ holdings })
    });
}

function renderHoldingsTable() {
    const tbody = $('holdings-tbody');
    const empty = $('holdings-empty');
    const table = $('holdings-table');
    if (!holdings.length) {
        tbody.innerHTML = '';
        empty.classList.remove('hidden');
        table.style.display = 'none';
        return;
    }
    empty.classList.add('hidden');
    table.style.display = '';
    tbody.innerHTML = holdings.map((h, i) => `
        <tr>
            <td><strong>${h.ticker}</strong></td>
            <td>${h.qty || '—'}</td>
            <td>${h.cost_basis ? '$' + Number(h.cost_basis).toFixed(2) : '—'}</td>
            <td><button class="remove-btn" data-idx="${i}" title="Remove">✕</button></td>
        </tr>`).join('');
    tbody.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            holdings.splice(Number(btn.dataset.idx), 1);
            renderHoldingsTable();
            savePortfolio();
        });
    });
}

function setupPortfolioForm() {
    $('add-holding-form').addEventListener('submit', async e => {
        e.preventDefault();
        const ticker = $('ticker-input').value.trim().toUpperCase();
        if (!ticker) return;
        const qty        = parseFloat($('qty-input').value)  || 0;
        const cost_basis = parseFloat($('cost-input').value) || 0;
        const existing   = holdings.find(h => h.ticker === ticker);
        if (existing) { existing.qty = qty || existing.qty; existing.cost_basis = cost_basis || existing.cost_basis; }
        else holdings.push({ ticker, qty, cost_basis });
        $('ticker-input').value = $('qty-input').value = $('cost-input').value = '';
        renderHoldingsTable();
        await savePortfolio();
    });
}

/* =====================================================
   CSV IMPORT
   ===================================================== */
function setupCSV() {
    const zone   = $('csv-drop-zone');
    const input  = $('csv-file-input');
    const status = $('csv-status');

    $('csv-browse-btn').addEventListener('click', () => input.click());
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => { if (input.files[0]) uploadCSV(input.files[0]); });
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) uploadCSV(e.dataTransfer.files[0]);
    });

    async function uploadCSV(file) {
        const form = new FormData();
        form.append('file', file);
        try {
            const res  = await fetch(`${API}/api/portfolio/csv`, { method: 'POST', body: form });
            const data = await res.json();
            if (res.ok) { holdings = data.holdings || []; renderHoldingsTable(); showCSVStatus(`✓ Imported ${data.count} holdings`, 'ok'); }
            else showCSVStatus(`✗ ${data.detail || 'Import failed'}`, 'err');
        } catch(e) { showCSVStatus('✗ Network error', 'err'); }
    }

    function showCSVStatus(msg, type) {
        status.textContent = msg;
        status.className   = `csv-status ${type}`;
        status.classList.remove('hidden');
        setTimeout(() => status.classList.add('hidden'), 4000);
    }
}

/* =====================================================
   PROFILE
   ===================================================== */
async function loadProfile() {
    try { const res = await fetch(`${API}/api/profile`); profile = await res.json(); applyProfileToUI(); }
    catch(e) { console.error('loadProfile', e); }
}

function applyProfileToUI() {
    const name = profile.name || '';
    $('profile-name-display').textContent = name || 'Set up profile';
    $('profile-risk-display').textContent = profile.risk_tolerance ? `${profile.risk_tolerance} · ${profile.investment_horizon || ''}` : '—';
    $('profile-avatar').textContent = name ? name[0].toUpperCase() : '?';
    $('profile-name').value = name;
    [...$('profile-risk').options].forEach(o => { o.selected = o.textContent === profile.risk_tolerance; });
    [...$('profile-horizon').options].forEach(o => { o.selected = o.textContent === profile.investment_horizon; });
    const focus = profile.focus || [];
    document.querySelectorAll('.chip').forEach(chip => chip.classList.toggle('active', focus.includes(chip.dataset.val)));
}

function setupProfile() {
    const overlay = $('profile-modal-overlay');
    $('profile-btn').addEventListener('click', () => { applyProfileToUI(); overlay.classList.remove('hidden'); });
    $('profile-modal-close').addEventListener('click', () => overlay.classList.add('hidden'));
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.add('hidden'); });
    document.querySelectorAll('.chip').forEach(chip => chip.addEventListener('click', () => chip.classList.toggle('active')));
    $('profile-form').addEventListener('submit', async e => {
        e.preventDefault();
        const focus   = [...document.querySelectorAll('.chip.active')].map(c => c.dataset.val);
        const payload = { name: $('profile-name').value.trim(), risk_tolerance: $('profile-risk').value, investment_horizon: $('profile-horizon').value, focus };
        await fetch(`${API}/api/profile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        profile = payload;
        applyProfileToUI();
        overlay.classList.add('hidden');
    });
}

/* =====================================================
   MORNING BRIEF
   ===================================================== */
function setupBrief() {
    $('generate-btn').addEventListener('click', generateBrief);
}

async function generateBrief() {
    const btn     = $('generate-btn');
    const spinner = $('brief-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont    = $('brief-container');
    const overallWrap = $('overall-brief-wrap');

    if (!holdings.length) { alert('Add holdings in the Portfolio tab first.'); switchTab('portfolio'); return; }

    btnText.textContent = 'Analyzing…';
    spinner.classList.remove('hidden');
    btn.disabled = true;
    cont.innerHTML = '';
    overallWrap.classList.add('hidden');
    overallWrap.innerHTML = '';

    // Show overall brief loading skeleton
    overallWrap.classList.remove('hidden');
    overallWrap.innerHTML = `<div class="overall-brief-card"><div class="overall-loading"><div class="spinner"></div><span>Generating portfolio overview…</span></div></div>`;

    try {
        // Fire both requests in parallel
        const [briefRes, overallRes] = await Promise.all([
            fetch(`${API}/api/brief`),
            fetch(`${API}/api/overall_brief`),
        ]);

        const [briefData, overallData] = await Promise.all([briefRes.json(), overallRes.json()]);

        // Render overall brief hero
        if (overallData && overallData.bluf) {
            overallWrap.innerHTML = buildOverallBriefCard(overallData);
        } else {
            overallWrap.classList.add('hidden');
        }

        // Render individual cards
        const briefs = briefData.brief || [];
        if (!briefs.length) {
            cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><h2>No news found today</h2><p>Try again later or add more tickers.</p></div>';
        } else {
            briefs.forEach((item, idx) => cont.appendChild(buildBriefCard(item, idx)));
        }
    } catch(e) {
        console.error(e);
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Error generating brief. Check server logs.</p></div>`;
    } finally {
        btnText.textContent = '✨ Generate Brief';
        spinner.classList.add('hidden');
        btn.disabled = false;
    }
}

function buildOverallBriefCard(data) {
    const sentClass = (data.portfolio_sentiment || 'Mixed').toLowerCase();
    const sentLabel = data.portfolio_sentiment || 'Mixed';
    const bodyParas = (data.body || '').split('\n').filter(Boolean).map(p => `<p>${p}</p>`).join('');
    return `
    <div class="overall-brief-card">
        <div class="overall-brief-meta">
            <span class="overall-tag">🌅 Morning Overview</span>
            <span class="badge ${sentClass === 'mixed' ? 'neutral' : sentClass}">${sentLabel}</span>
        </div>
        <div class="overall-brief-headline">${data.bluf || ''}</div>
        <div class="overall-brief-body">${bodyParas}</div>
        ${data.watch_item ? `<div class="overall-brief-footer"><span style="font-size:.75rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-3)">Watch today:</span><span style="font-size:.85rem;color:var(--act-review)">👁 ${data.watch_item}</span></div>` : ''}
    </div>`;
}

function buildBriefCard(item, idx) {
    const card      = document.createElement('div');
    card.className  = 'brief-card';
    card.style.animationDelay = `${idx * 0.08}s`;

    const sentiment = (item.sentiment || 'Neutral').toLowerCase();
    const impact    = (item.impact    || 'Low').toLowerCase();
    const signal    = (item.action_signal || 'Monitor').toLowerCase();

    const bullets  = (item.bullets || []).map(b => `<li>${b}</li>`).join('');
    const drivers  = (item.key_drivers || []).map(d => `<span class="driver-chip">${d}</span>`).join('');
    const posBlock = (item.qty || item.cost_basis)
        ? `<div class="position-meta">Position: <span>${item.qty ?? '—'} units</span> @ <span>$${item.cost_basis ? Number(item.cost_basis).toFixed(2) : '—'}</span></div>` : '';

    card.innerHTML = `
        <div class="brief-card-header ${sentiment}">
            <div class="brief-ticker">${item.ticker}</div>
            <div class="brief-badges">
                <span class="badge ${sentiment}">${item.sentiment || 'Neutral'}</span>
                <span class="badge ${impact}">${item.impact || 'Low'} Impact</span>
                <span class="badge" style="background:transparent;border:none;color:var(--act-${signal})">
                    <span class="signal-dot signal-${signal}"></span> ${item.action_signal || 'Monitor'}
                </span>
            </div>
        </div>
        <div class="brief-card-body">
            <div class="brief-section">
                <h4>Latest News</h4>
                <p class="brief-headline">${item.headline || ''}</p>
                <ul class="bullet-list">${bullets}</ul>
                ${drivers ? `<div class="driver-chips" style="margin-top:.75rem">${drivers}</div>` : ''}
            </div>
            <div class="brief-section">
                <h4>Position Insight</h4>
                <div class="insight-box"><p>${item.position_insight || '—'}</p></div>
                ${posBlock}
            </div>
        </div>`;
    return card;
}

/* =====================================================
   ANALYTICS
   ===================================================== */
function setupAnalytics() {
    $('refresh-analytics-btn').addEventListener('click', loadAnalytics);
}

async function loadAnalytics() {
    const btn     = $('refresh-analytics-btn');
    const spinner = $('analytics-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont    = $('analytics-container');

    if (!holdings.length) { alert('Add holdings first.'); switchTab('portfolio'); return; }
    btnText.textContent = 'Loading…';
    spinner.classList.remove('hidden');
    btn.disabled = true;
    cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><p>Fetching market data…</p></div>';

    try {
        const res  = await fetch(`${API}/api/analytics`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderAnalytics(data, cont);
    } catch(e) {
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Analytics failed: ${e.message}</p></div>`;
    } finally {
        btnText.textContent = '↻ Refresh Analytics';
        spinner.classList.add('hidden');
        btn.disabled = false;
    }
}

/* ---- Sparkline helper ---- */
function buildSparkline(prices, width = 64, height = 28) {
    if (!prices || prices.length < 2) return '<span style="color:var(--text-3);font-size:.75rem">—</span>';
    const min  = Math.min(...prices);
    const max  = Math.max(...prices);
    const range = max - min || 1;
    const isPos = prices[prices.length - 1] >= prices[0];
    const pts   = prices.map((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const cls   = isPos ? 'sparkline-pos' : 'sparkline-neg';
    return `<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline class="sparkline-line ${cls}" points="${pts}"/>
    </svg>`;
}

function renderAnalytics(data, cont) {
    const m     = data.portfolio_metrics || {};
    const div   = data.diversification   || {};
    const hs    = data.holdings          || [];
    const total = data.total_value       || 0;

    const retClass = m.annual_return_pct >= 0 ? 'pos' : 'neg';
    const retSign  = m.annual_return_pct >= 0 ? '+' : '';

    /* ---- Stat cards with tooltips ---- */
    const statsHtml = `
    <div class="analytics-grid">
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Portfolio Value']}">Portfolio Value</span>
            <span class="stat-value">$${total.toLocaleString('en-US',{maximumFractionDigits:2})}</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Annual Return (est.)']}">Annual Return (est.)</span>
            <span class="stat-value ${retClass}">${m.annual_return_pct != null ? retSign+m.annual_return_pct+'%' : '—'}</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Annual Volatility']}">Annual Volatility</span>
            <span class="stat-value">${m.annual_volatility_pct != null ? m.annual_volatility_pct+'%' : '—'}</span>
            <span class="stat-sub">Annualised std-dev</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Sharpe Ratio']}">Sharpe Ratio</span>
            <span class="stat-value ${m.sharpe_ratio >= 1 ? 'pos' : m.sharpe_ratio < 0 ? 'neg' : ''}">${m.sharpe_ratio ?? '—'}</span>
            <span class="stat-sub">RF rate 4.5%</span>
        </div>
    </div>`;

    /* ---- Diversification ring ---- */
    const score    = div.score || 0;
    const circ     = 2 * Math.PI * 34;
    const filled   = (score / 100) * circ;
    const ringColor = score >= 70 ? 'var(--bullish)' : score >= 45 ? 'var(--brand)' : 'var(--bearish)';
    const flags     = (div.flags || []).map(f => `<div class="div-flags">⚠ ${f}</div>`).join('');

    /* ---- Sector bars ---- */
    const sectors = div.sector_breakdown || {};
    const sectorBars = Object.entries(sectors).sort((a,b) => b[1]-a[1]).map(([s, pct]) => `
        <div class="sector-row">
            <div class="sector-name">${s}</div>
            <div class="sector-bar-bg"><div class="sector-bar-fill" style="width:${pct}%"></div></div>
            <div class="sector-pct">${Math.round(pct)}%</div>
        </div>`).join('');

    /* ---- Holdings detail with sparklines ---- */
    const holdRows = hs.map(h => {
        const pnl    = h.gain_loss  ?? 0;
        const pnlPct = h.gain_pct   ?? 0;
        const pnlCls = pnl >= 0 ? 'pos' : 'neg';
        const sign   = pnl >= 0 ? '+' : '';
        const spark  = buildSparkline(h.sparkline || []);
        return `<tr>
            <td><strong>${h.ticker}</strong></td>
            <td class="sparkline-cell">${spark}</td>
            <td>$${h.current_price?.toFixed(2) ?? '—'}</td>
            <td class="has-tooltip" data-tip="${TIPS['Weight']}">${h.weight_pct ?? '—'}%</td>
            <td class="${pnlCls} has-tooltip" data-tip="${TIPS['P&L']}">${sign}$${Math.abs(pnl).toFixed(2)}</td>
            <td class="${pnlCls}">${sign}${pnlPct.toFixed(2)}%</td>
            <td class="has-tooltip" data-tip="${TIPS['Annual Volatility']}">${h.annual_volatility_pct != null ? h.annual_volatility_pct+'%' : '—'}</td>
            <td><span style="color:var(--text-2);font-size:.78rem">${h.sector || '—'}</span></td>
        </tr>`;
    }).join('');

    cont.innerHTML = `
        ${statsHtml}
        <div class="analytics-row">
            <div class="analytics-card">
                <h3><span class="has-tooltip" data-tip="${TIPS['Diversification Score']}">Diversification</span></h3>
                <div class="div-score-wrap">
                    <div class="div-ring">
                        <svg width="80" height="80" viewBox="0 0 80 80">
                            <circle class="div-ring-bg"   cx="40" cy="40" r="34"/>
                            <circle class="div-ring-fill" cx="40" cy="40" r="34" stroke="${ringColor}"
                                stroke-dasharray="${filled} ${circ}"/>
                        </svg>
                        <div class="div-ring-label" style="color:${ringColor}">${score}</div>
                    </div>
                    <div class="div-score-meta">
                        <div class="div-label">${div.label || '—'}</div>
                        <div style="font-size:.8rem;color:var(--text-3)">${hs.length} position${hs.length!==1?'s':''}</div>
                        ${flags}
                    </div>
                </div>
            </div>
            <div class="analytics-card">
                <h3>Sector Breakdown</h3>
                <div class="sector-bars">${sectorBars || '<p style="color:var(--text-3);font-size:.85rem">—</p>'}</div>
            </div>
        </div>
        <div class="analytics-card" style="margin-bottom:1rem">
            <h3>Holdings Detail</h3>
            <div style="overflow-x:auto">
                <table class="holdings-table">
                    <thead><tr>
                        <th>Ticker</th><th>30d Chart</th><th>Price</th>
                        <th>Weight</th><th>P&L $</th><th>P&L %</th><th>Volatility</th><th>Sector</th>
                    </tr></thead>
                    <tbody>${holdRows}</tbody>
                </table>
            </div>
        </div>`;
}

/* =====================================================
   ACTION ITEMS
   ===================================================== */
function setupActions() {
    $('refresh-actions-btn').addEventListener('click', loadActions);
}

async function loadActions() {
    const btn     = $('refresh-actions-btn');
    const spinner = $('actions-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont    = $('actions-container');

    if (!holdings.length) { alert('Add holdings first.'); switchTab('portfolio'); return; }
    btnText.textContent = 'Analyzing…';
    spinner.classList.remove('hidden');
    btn.disabled = true;
    cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><p>Running portfolio analysis…</p></div>';

    try {
        const res  = await fetch(`${API}/api/actions`);
        const data = await res.json();
        renderActions(data.items || [], cont);
    } catch(e) {
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Failed: ${e.message}</p></div>`;
    } finally {
        btnText.textContent = '↻ Refresh Suggestions';
        spinner.classList.add('hidden');
        btn.disabled = false;
    }
}

function renderActions(items, cont) {
    if (!items.length) {
        cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><h2>No suggestions</h2></div>';
        return;
    }
    const html = items.map(item => `
        <div class="action-item ${item.type}">
            <span class="action-icon">${item.icon}</span>
            <div class="action-text">
                <strong>${item.title}</strong>
                <span class="sub">${item.sub}</span>
            </div>
        </div>`).join('');

    cont.innerHTML = `
        <div class="actions-panel" style="animation: fadeUp 0.4s ease forwards">
            <h3>Personalized Recommendations</h3>
            <div class="action-items-list">${html}</div>
        </div>`;
}
