/* =====================================================
   HEIMDALL – App Logic
   ===================================================== */

const API = '';

/* ---- State ---- */
let holdings = [];
let profile = {};
let activeTab = 'brief';
let tabs = {}; // populated after DOM ready

/* ---- DOM ---- */
const $ = id => document.getElementById(id);

/**
 * AUTHORIZED FETCH WRAPPER
 */
async function fetchAuthorized(url, options = {}) {
    const token = await getToken();
    const headers = {
        ...options.headers,
        'Authorization': token ? `Bearer ${token}` : ''
    };
    return fetch(url, { ...options, headers });
}

/* =====================================================
   TOOLTIPS for financial terms
   ===================================================== */
const TIPS = {
    'Sharpe Ratio': "Measures return per unit of risk. Above 1.0 = good, above 2.0 = excellent. Below 0 means you'd be better off in cash.",
    'Annual Volatility': 'How much the portfolio swings year-to-year (std dev of daily returns x sqrt(252)). Higher = riskier.',
    'Annual Return (est.)': 'Estimated annualised return based on last 1 year of price data. Past performance does not guarantee future results.',
    'Portfolio Value': 'Sum of (current price x quantity) across all your holdings.',
    'Diversification Score': 'A 0-100 score based on number of holdings, sector spread, and single-name concentration. Higher is safer.',
    'P&L': 'Profit & Loss: (current price - your avg cost) x quantity. Unrealised until you sell.',
    'Weight': 'What percentage of your total portfolio value this position makes up.',
    'Beta': 'Sensitivity to S&P 500 moves. Beta 1.5 = stock typically moves 1.5x the market. Above 1 = amplified swings; below 1 = more defensive.',
    'VaR (1-day, 95%)': 'Value at Risk: based on the last year of daily returns, there is a 95% chance your portfolio will not lose more than this percent in a single trading day.',
    'VaR (1-month, 95%)': 'Monthly Value at Risk: estimated worst-case 1-month loss at 95% confidence, scaled from daily VaR.',
    'P/E Ratio': 'Price-to-Earnings: how much you pay per dollar of earnings. "fwd" uses next-year analyst estimates; "ttm" uses the last 12 months.',
    'P/S Ratio': 'Price-to-Sales: market cap divided by annual revenue. Useful for unprofitable or high-growth companies.',
    'Portfolio Beta': 'Weighted-average beta of the portfolio. A portfolio beta of 1.3 means a 10% market drop would typically hurt the portfolio ~13%.',
};

/* =====================================================
   INIT
   ===================================================== */
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Auth0
    const client = await initAuth();
    if (!client) {
        alert("Auth0 failed to initialize. Check console.");
        return;
    }

    const authenticated = await isAuthenticated();
    
    // Toggle screens based on auth status
    document.body.classList.remove('auth-loading');
    $('auth-loading-screen').classList.add('hidden');

    $('login-btn').addEventListener('click', login);
    $('logout-btn').addEventListener('click', logout);

    if (!authenticated) {
        showLogin();
        return;
    }

    showApp();

    // 2. Setup standard UI
    tabs.brief = { nav: $('nav-brief'), panel: $('tab-brief') };
    tabs.analytics = { nav: $('nav-analytics'), panel: $('tab-analytics') };
    tabs.actions = { nav: $('nav-actions'), panel: $('tab-actions') };
    tabs.portfolio = { nav: $('nav-portfolio'), panel: $('tab-portfolio') };

    $('current-date').textContent = new Date().toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
    });

    // 3. Load user data
    const user = await getUser();
    updateProfileDisplay(user);

    await Promise.all([loadPortfolio(), loadProfile()]);
    
    // 4. Setup listeners
    setupNav();
    setupPortfolioForm();
    setupCSV();
    setupProfile();
    setupBrief();
    setupAnalytics();
    setupActions();
    setupSidebar();
    setupSnapTrade();
});

function showLogin() {
    $('login-screen').classList.remove('hidden');
    $('sidebar').classList.add('hidden');
    $('main-layout').classList.add('hidden');
}

function showApp() {
    $('login-screen').classList.add('hidden');
    $('sidebar').classList.remove('hidden');
    $('main-layout').classList.remove('hidden');
}

function updateProfileDisplay(user) {
    if (!user) return;
    const name = user.name || user.nickname || 'User';
    $('profile-name-display').textContent = name;
    
    if (user.picture) {
        $('profile-avatar-img').src = user.picture;
        $('profile-avatar-img').style.display = 'block';
        $('profile-avatar').style.display = 'none';
    } else {
        $('profile-avatar').textContent = name[0].toUpperCase();
    }
}

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
        const res = await fetchAuthorized(`${API}/api/portfolio`);
        const data = await res.json();
        holdings = data.holdings || [];
        renderHoldingsTable();
    } catch (e) { console.error('loadPortfolio', e); }
}

async function savePortfolio() {
    await fetchAuthorized(`${API}/api/portfolio`, {
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
        const qty = parseFloat($('qty-input').value) || 0;
        const cost_basis = parseFloat($('cost-input').value) || 0;
        const existing = holdings.find(h => h.ticker === ticker);
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
    const zone = $('csv-drop-zone');
    const input = $('csv-file-input');
    const status = $('csv-status');

    $('csv-browse-btn').addEventListener('click', () => input.click());
    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => { if (input.files[0]) uploadCSV(input.files[0]); });
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('drag-over');
        if (e.dataTransfer.files[0]) uploadCSV(e.dataTransfer.files[0]);
    });

    async function uploadCSV(file) {
        const form = new FormData();
        form.append('file', file);
        try {
            const res = await fetchAuthorized(`${API}/api/portfolio/csv`, { method: 'POST', body: form });
            const data = await res.json();
            if (res.ok) { holdings = data.holdings || []; renderHoldingsTable(); showCSVStatus(`✓ Imported ${data.count} holdings`, 'ok'); }
            else showCSVStatus(`✗ ${data.detail || 'Import failed'}`, 'err');
        } catch (e) { showCSVStatus('✗ Network error', 'err'); }
    }

    function showCSVStatus(msg, type) {
        status.textContent = msg;
        status.className = `csv-status ${type}`;
        status.classList.remove('hidden');
        setTimeout(() => status.classList.add('hidden'), 4000);
    }
}

/* =====================================================
   PROFILE
   ===================================================== */
async function loadProfile() {
    try { const res = await fetchAuthorized(`${API}/api/profile`); profile = await res.json(); applyProfileToUI(); }
    catch (e) { console.error('loadProfile', e); }
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
        const focus = [...document.querySelectorAll('.chip.active')].map(c => c.dataset.val);
        const payload = { name: $('profile-name').value.trim(), risk_tolerance: $('profile-risk').value, investment_horizon: $('profile-horizon').value, focus };
        await fetchAuthorized(`${API}/api/profile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
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
    const btn = $('generate-btn');
    const spinner = $('brief-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont = $('brief-container');
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
            fetchAuthorized(`${API}/api/brief`),
            fetchAuthorized(`${API}/api/overall_brief`),
        ]);

        let briefData;
        if (!briefRes.ok) {
            const err = await briefRes.json();
            throw new Error(err.detail || 'Failed to fetch brief');
        } else {
            briefData = await briefRes.json();
        }

        let overallData;
        if (!overallRes.ok) {
            try {
                const err = await overallRes.json();
                console.warn('Overall brief failed:', err);
            } catch (e) {}
            overallData = { bluf: null }; // Fallback safe object
        } else {
            overallData = await overallRes.json();
        }

        // Render overall brief hero
        if (overallData && overallData.bluf) {
            overallWrap.innerHTML = buildOverallBriefCard(overallData);
            const playBtn = document.getElementById('play-brief-btn');
            if (playBtn) {
                let currentAudio = null;
                playBtn.addEventListener('click', async () => {
                    if (currentAudio) {
                        if (currentAudio.paused) currentAudio.play();
                        else currentAudio.pause();
                        playBtn.innerHTML = currentAudio.paused ? '🔊 Play Audio' : '⏸ Pause Audio';
                        return;
                    }
                    playBtn.textContent = 'Loading...';
                    playBtn.disabled = true;
                    try {
                        const fallbackGreeting = profile.name ? `Good morning, ${profile.name}. ` : 'Good morning. ';
                        const fallbackText = `${fallbackGreeting}${overallData.bluf}. ${overallData.macro_environment || ''}`;
                        const textToRead = (overallData.audio_script || fallbackText).replace(/\*/g, '');
                        
                        const ttsRes = await fetchAuthorized(`${API}/api/tts`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ text: textToRead })
                        });
                        if (!ttsRes.ok) throw new Error(await ttsRes.text());
                        const blob = await ttsRes.blob();
                        currentAudio = new Audio(URL.createObjectURL(blob));
                        currentAudio.onended = () => { playBtn.innerHTML = '🔊 Play Audio'; };
                        currentAudio.play();
                        playBtn.innerHTML = '⏸ Pause Audio';
                    } catch (err) {
                        alert('Audio generation failed: ' + err.message);
                        playBtn.innerHTML = '🔊 Play Audio';
                    } finally {
                        playBtn.disabled = false;
                    }
                });
            }
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
    } catch (e) {
        console.error(e);
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Error generating brief. Check server logs.</p></div>`;
    } finally {
        btnText.textContent = 'Generate Brief';
        spinner.classList.add('hidden');
        btn.disabled = false;
    }
}

/* ---- Entity Exposure Network (Macro Web) ---- */
function buildMacroWeb(exposures) {
    if (!exposures || !exposures.length) return '';
    
    const themes = exposures.map(e => e.theme);
    const affectedT = new Set();
    exposures.forEach(e => (e.affected_tickers||[]).forEach(t => affectedT.add(t)));
    const tickers = Array.from(affectedT);
    
    const H = Math.max(160, Math.max(themes.length, tickers.length) * 40);
    const W = 460;
    
    const themePitch = H / (themes.length + 1);
    const tickerPitch = H / (tickers.length + 1);
    
    const lx = 160; 
    const rx = W - 100;
    
    let edges = '';
    let nodesHtml = '';
    
    exposures.forEach((exp, i) => {
        const ty = (i + 1) * themePitch;
        nodesHtml += `
            <div style="position:absolute; left:10px; top:${ty - 10}px; 
                        width: ${lx - 25}px; text-align:right; 
                        font-size:0.75rem; color:var(--text-1); font-weight:600;
                        white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${exp.theme}">
                ${exp.theme}
            </div>
            <div class="macro-node" style="left:${lx-4}px; top:${ty-4}px; background:var(--text-1)"></div>
        `;
        
        (exp.affected_tickers||[]).forEach(t => {
            const j = tickers.indexOf(t);
            if (j === -1) return;
            const rty = (j + 1) * tickerPitch;
            const color = exp.impact_direction === 'positive' ? 'var(--bullish)' 
                        : exp.impact_direction === 'negative' ? 'var(--bearish)' 
                        : 'var(--text-3)';
            edges += `<path d="M ${lx} ${ty} C ${lx + 80} ${ty}, ${rx - 80} ${rty}, ${rx} ${rty}" 
                            fill="none" stroke="${color}" stroke-width="1.5" opacity="0.6"/>`;
        });
    });
    
    tickers.forEach((t, j) => {
        const y = (j + 1) * tickerPitch;
        nodesHtml += `
            <div class="macro-node" style="left:${rx-4}px; top:${y-4}px;"></div>
            <div style="position:absolute; left:${rx + 12}px; top:${y - 8}px; 
                        font-size:0.75rem; color:var(--text-2); font-weight:600;">
                ${t}
            </div>
        `;
    });
    
    return `
    <div class="brief-article-section" style="margin-top:1.5rem;">
        <div class="brief-article-label">Entity Exposure Network</div>
        <div style="position:relative; width:100%; max-width:${W}px; height:${H}px; overflow-x:auto;">
            <svg xmlns="http://www.w3.org/2000/svg" style="position:absolute; left:0; top:0; width:${W}px; height:${H}px; pointer-events:none;">
                ${edges}
            </svg>
            <div style="position:absolute; left:0; top:0; width:${W}px; height:${H}px; pointer-events:none;">
                ${nodesHtml}
            </div>
        </div>
    </div>`;
}

function buildOverallBriefCard(data) {
    const sentClass = (data.portfolio_sentiment || 'Mixed').toLowerCase();
    const sentLabel = data.portfolio_sentiment || 'Mixed';

    // Build article sections from new structured schema
    const sections = [];

    if (data.macro_environment) {
        sections.push(`
            <div class="brief-article-section">
                <div class="brief-article-label">Macro & Geopolitics</div>
                <p class="brief-article-body">${data.macro_environment}</p>
            </div>`);
    }

    if (data.portfolio_impact) {
        sections.push(`
            <div class="brief-article-section">
                <div class="brief-article-label">Portfolio Impact</div>
                <p class="brief-article-body">${data.portfolio_impact}</p>
            </div>`);
    }

    const riskOpp = [];
    if (data.key_risk) {
        riskOpp.push(`<div class="brief-risk-item danger"><em>Risk:</em> ${data.key_risk}</div>`);
    }
    if (data.opportunity) {
        riskOpp.push(`<div class="brief-risk-item success"><em>Opportunity:</em> ${data.opportunity}</div>`);
    }
    if (riskOpp.length) {
        sections.push(`<div class="brief-article-section">${riskOpp.join('')}</div>`);
    }

    // Fallback to old 'body' field if new schema not present
    if (!sections.length && data.body) {
        const bodyParas = data.body.split('\n').filter(Boolean).map(p => `<p class="brief-article-body">${p}</p>`).join('');
        sections.push(`<div class="brief-article-section">${bodyParas}</div>`);
    }

    if (data.macro_exposures && data.macro_exposures.length) {
        sections.push(buildMacroWeb(data.macro_exposures));
    }

    return `
    <div class="overall-brief-card">
        <div class="overall-brief-meta">
            <span class="overall-tag">Morning Overview</span>
            <span class="badge ${sentClass === 'mixed' ? 'neutral' : sentClass}">${sentLabel}</span>
            <button class="action-btn secondary" id="play-brief-btn" style="padding: 0.35rem 0.75rem; font-size: 0.75rem; margin-left: auto;">
                🔊 Play Audio
            </button>
        </div>
        <div class="overall-brief-headline">${data.bluf || ''}</div>
        <div class="overall-brief-sections">${sections.join('')}</div>
    </div>`;
}


function buildBriefCard(item, idx) {
    const card = document.createElement('div');
    card.className = 'brief-card';
    card.style.animationDelay = `${idx * 0.08}s`;

    const sentiment = (item.sentiment || 'Neutral').toLowerCase();
    const impact = (item.impact || 'Low').toLowerCase();
    const signal = (item.action_signal || 'Monitor').toLowerCase();

    const bullets = (item.bullets || []).map(b => `<li>${b}</li>`).join('');
    const drivers = (item.key_drivers || []).map(d => `<span class="driver-chip">${d}</span>`).join('');
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
    const btn = $('refresh-analytics-btn');
    const spinner = $('analytics-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont = $('analytics-container');

    if (!holdings.length) { alert('Add holdings first.'); switchTab('portfolio'); return; }
    btnText.textContent = 'Loading…';
    spinner.classList.remove('hidden');
    btn.disabled = true;
    cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><p>Fetching market data…</p></div>';

    try {
        const res = await fetchAuthorized(`${API}/api/analytics`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderAnalytics(data, cont);
    } catch (e) {
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Analytics failed: ${e.message}</p></div>`;
    } finally {
        btnText.textContent = 'Refresh Analytics';
        spinner.classList.add('hidden');
        btn.disabled = false;
    }
}

/* ---- Sparkline helper ---- */
function buildSparkline(prices, width = 64, height = 28) {
    if (!prices || prices.length < 2) return '<span style="color:var(--text-3);font-size:.75rem">—</span>';
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const isPos = prices[prices.length - 1] >= prices[0];
    const pts = prices.map((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const cls = isPos ? 'sparkline-pos' : 'sparkline-neg';
    return `<svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline class="sparkline-line ${cls}" points="${pts}"/>
    </svg>`;
}

/* ---- Benchmark comparison chart ---- */
function buildBenchmarkChart(bmark) {
    if (!bmark || !bmark.dates || bmark.dates.length < 2) return '';
    const port = bmark.portfolio_cumulative;
    const spy = bmark.spy_cumulative;
    const allV = [...port, ...spy];
    const minV = Math.min(...allV), maxV = Math.max(...allV);
    const range = (maxV - minV) || 1;
    const W = 560, H = 140;
    const pad = { t: 12, b: 20, l: 44, r: 10 };
    const cw = W - pad.l - pad.r;
    const ch = H - pad.t - pad.b;
    const xs = i => ((i / (port.length - 1)) * cw).toFixed(1);
    const ys = v => (ch - ((v - minV) / range) * ch).toFixed(1);

    const pPts = port.map((v, i) => `${xs(i)},${ys(v)}`).join(' ');
    const sPts = spy.map((v, i) => `${xs(i)},${ys(v)}`).join(' ');

    // Y-axis ticks
    const ticks = 4;
    const yLabels = Array.from({ length: ticks + 1 }, (_, k) => {
        const v = minV + (range * k / ticks);
        const y = ys(v);
        return `<text class="ch-axis-lbl" x="-6" y="${y}" text-anchor="end" dominant-baseline="middle">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</text>`;
    }).join('');

    const zeroY = ys(0);
    const alphaClass = bmark.alpha >= 0 ? 'pos' : 'neg';
    const alphaSign = bmark.alpha >= 0 ? '+' : '';
    const portSign = bmark.portfolio_total_return_pct >= 0 ? '+' : '';
    const spySign = bmark.spy_total_return_pct >= 0 ? '+' : '';
    const portRet = bmark.portfolio_total_return_pct;
    const spyRet = bmark.spy_total_return_pct;

    return `
    <div class="analytics-card">
        <div class="bench-header">
            <h3>Performance vs S&P 500 (1yr)</h3>
            <div class="bench-returns">
                <span class="bench-tag" style="background:var(--brand-dim);border-color:var(--brand)"><span class="bench-dot" style="background:var(--brand)"></span>Portfolio: <strong class="${portRet >= 0 ? 'pos' : 'neg'}">${portSign}${portRet}%</strong></span>
                <span class="bench-tag"><span class="bench-dot" style="background:var(--text-3)"></span>SPY: <strong>${spySign}${spyRet}%</strong></span>
                <span class="bench-tag" style="background:var(--brand-dim);border-color:var(--border-active)">Alpha: <strong class="${alphaClass}">${alphaSign}${bmark.alpha}%</strong></span>
            </div>
        </div>
        <svg class="bench-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <g transform="translate(${pad.l},${pad.t})">
                <line x1="0" y1="${zeroY}" x2="${cw}" y2="${zeroY}" class="ch-zero-line"/>
                ${yLabels}
                <polyline class="ch-line-spy" points="${sPts}"/>
                <polyline class="ch-line-port" points="${pPts}"/>
            </g>
        </svg>
    </div>`;
}


/* ---- Correlation cluster map (force-directed) ---- */
function buildCorrWeb(corrData) {
    if (!corrData || !corrData.tickers || corrData.tickers.length < 2) return '';
    return `
    <div class="analytics-card">
        <h3>Correlation Cluster Map</h3>
        <p class="corr-desc">Holdings are pulled together by correlation strength &mdash; <span style="color:var(--text-1)">clustered = move together</span>, distant = uncorrelated. <span style="color:var(--text-3)">Dark edges = inverse</span>. Watch the physics settle.</p>
        <div style="display:flex;justify-content:center; touch-action:none;">
            <svg id="corr-svg" width="460" height="390" class="corr-canvas" xmlns="http://www.w3.org/2000/svg" style="border-radius: var(--radius-md)"></svg>
        </div>
        <p id="corr-note" class="corr-desc" style="margin-top:.4rem;text-align:center"></p>
    </div>`;
}

function initCorrSim(corrData) {
    const svg = document.getElementById('corr-svg');
    if (!svg || !corrData) return;
    const W = 460, H = 390;
    const { tickers, matrix } = corrData;
    const n = tickers.length;
    const NR = Math.max(16, Math.min(26, 200 / n));

    const nodes = tickers.map(t => ({
        t,
        x: W / 2 + (Math.random() - 0.5) * 60,
        y: H / 2 + (Math.random() - 0.5) * 60,
        vx: 0, vy: 0
    }));

    const K_REPEL = 10000;
    const K_SPRING = 0.01;
    const DAMPING = 0.80;
    const BASE_DIST = Math.min(W, H) * 0.50;
    let iter = 0;
    let rafId = null;
    let draggedNode = null;
    let hoveredNode = null;

    let svgEdges = [];
    let svgNodes = [];

    // Initialize SVG elements
    const edgesGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const nodesGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    svg.appendChild(edgesGroup);
    svg.appendChild(nodesGroup);

    for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
            const corr = matrix[i][j];
            if (Math.abs(corr) < 0.25) continue;
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            const alpha = Math.min(0.92, 0.15 + Math.abs(corr) * 0.77);
            const baseStroke = corr > 0 ? `rgba(255,255,255,${alpha})` : `rgba(100,100,100,${alpha})`;
            line.setAttribute("stroke", baseStroke);
            line.setAttribute("stroke-width", Math.max(1, Math.abs(corr) * 5).toString());
            line.setAttribute("stroke-linecap", "round");
            line.style.transition = "stroke 0.2s, opacity 0.2s";
            edgesGroup.appendChild(line);
            svgEdges.push({ i, j, corr, el: line, baseStroke });
        }
    }

    for (let i = 0; i < n; i++) {
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.style.cursor = "grab";
        
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", NR.toString());
        circle.setAttribute("fill", "#0a0a0a");
        circle.setAttribute("stroke", "#ffffff");
        circle.setAttribute("stroke-width", "1.5");
        circle.style.transition = "fill 0.2s, stroke 0.2s";
        g.appendChild(circle);
        
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.textContent = tickers[i];
        const fs = Math.max(8, Math.min(11, 130 / n));
        text.setAttribute("font-size", fs.toString());
        text.setAttribute("font-family", "Inter,system-ui,sans-serif");
        text.setAttribute("font-weight", "700");
        text.setAttribute("text-anchor", "middle");
        text.setAttribute("dominant-baseline", "central");
        text.setAttribute("dy", "1");
        text.setAttribute("fill", "#ffffff");
        text.style.pointerEvents = "none";
        g.appendChild(text);
        
        nodesGroup.appendChild(g);
        svgNodes.push({ i, g, el: circle });

        // Interactivity
        g.addEventListener('pointerdown', e => {
            draggedNode = nodes[i];
            draggedNode.vx = 0; draggedNode.vy = 0;
            iter = 0;
            if (!rafId) tick();
            g.setPointerCapture(e.pointerId);
            e.stopPropagation();
        });
        g.addEventListener('pointerenter', () => { hoveredNode = i; if (!rafId) tick(); });
        g.addEventListener('pointerleave', () => { if (hoveredNode === i) hoveredNode = null; if (!rafId) tick(); });
    }

    svg.addEventListener('pointermove', e => {
        if (draggedNode) {
            const rect = svg.getBoundingClientRect();
            draggedNode.x = e.clientX - rect.left;
            draggedNode.y = e.clientY - rect.top;
            iter = 0;
            if (!rafId) tick();
        }
    });

    const endDrag = () => {
        if (draggedNode) {
            draggedNode = null;
            if (!rafId) tick();
        }
    };
    svg.addEventListener('pointerup', endDrag);
    svg.addEventListener('pointercancel', endDrag);

    function step() {
        const fx = new Float64Array(n);
        const fy = new Float64Array(n);
        for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
                const dx = nodes[j].x - nodes[i].x;
                const dy = nodes[j].y - nodes[i].y;
                const d = Math.sqrt(dx * dx + dy * dy) || 0.1;
                const nx = dx / d, ny = dy / d;
                const safeD = Math.max(10, d);
                const frep = K_REPEL / (safeD * safeD);
                fx[i] -= frep * nx; fy[i] -= frep * ny;
                fx[j] += frep * nx; fy[j] += frep * ny;
                const corr = matrix[i][j];
                const ideal = BASE_DIST * (1 - corr);
                const fsp = K_SPRING * (d - ideal);
                fx[i] += fsp * nx; fy[i] += fsp * ny;
                fx[j] -= fsp * nx; fy[j] -= fsp * ny;
            }
            const m = NR + 10;
            if (nodes[i].x < m) fx[i] += (m - nodes[i].x) * 0.55;
            if (nodes[i].x > W - m) fx[i] -= (nodes[i].x - (W - m)) * 0.55;
            if (nodes[i].y < m) fy[i] += (m - nodes[i].y) * 0.55;
            if (nodes[i].y > H - m) fy[i] -= (nodes[i].y - (H - m)) * 0.55;
            fx[i] += (W / 2 - nodes[i].x) * 0.003;
            fy[i] += (H / 2 - nodes[i].y) * 0.003;
        }

        for (let i = 0; i < n; i++) {
            if (nodes[i] === draggedNode) continue;
            const clampF = 50;
            const safeFx = Math.max(-clampF, Math.min(clampF, fx[i]));
            const safeFy = Math.max(-clampF, Math.min(clampF, fy[i]));
            nodes[i].vx = (nodes[i].vx + safeFx) * DAMPING;
            nodes[i].vy = (nodes[i].vy + safeFy) * DAMPING;
            nodes[i].x = Math.max(NR, Math.min(W - NR, nodes[i].x + nodes[i].vx));
            nodes[i].y = Math.max(NR, Math.min(H - NR, nodes[i].y + nodes[i].vy));
        }
        iter++;
    }

    function draw() {
        for (const edge of svgEdges) {
            const n1 = nodes[edge.i];
            const n2 = nodes[edge.j];
            edge.el.setAttribute("x1", n1.x.toFixed(1));
            edge.el.setAttribute("y1", n1.y.toFixed(1));
            edge.el.setAttribute("x2", n2.x.toFixed(1));
            edge.el.setAttribute("y2", n2.y.toFixed(1));

            if (hoveredNode !== null) {
                if (edge.i === hoveredNode || edge.j === hoveredNode) {
                    edge.el.setAttribute("stroke", "var(--brand)");
                    edge.el.setAttribute("opacity", "1");
                } else {
                    edge.el.setAttribute("stroke", edge.baseStroke);
                    edge.el.setAttribute("opacity", "0.15");
                }
            } else {
                edge.el.setAttribute("stroke", edge.baseStroke);
                edge.el.setAttribute("opacity", "1");
            }
        }
        
        for (const { i, g, el } of svgNodes) {
            const node = nodes[i];
            g.setAttribute("transform", `translate(${node.x.toFixed(1)}, ${node.y.toFixed(1)})`);

            if (hoveredNode !== null) {
                if (i === hoveredNode) {
                    el.setAttribute("stroke", "var(--brand)");
                    el.setAttribute("fill", "#1a2235");
                } else {
                    const connected = svgEdges.some(e => (e.i === hoveredNode && e.j === i) || (e.j === hoveredNode && e.i === i));
                    if (connected) {
                        el.setAttribute("stroke", "#4f9eff");
                        el.setAttribute("fill", "#0a0a0a");
                    } else {
                        el.setAttribute("stroke", "#333333");
                        el.setAttribute("fill", "#0a0a0a");
                    }
                }
            } else {
                el.setAttribute("stroke", "#ffffff");
                el.setAttribute("fill", "#0a0a0a");
            }
        }
    }

    let maxC = 0, maxPair = '';
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++)
        if (matrix[i][j] > maxC) { maxC = matrix[i][j]; maxPair = `${tickers[i]} & ${tickers[j]}`; }
    if (maxC > 0.3) {
        const note = document.getElementById('corr-note');
        if (note) note.textContent = `Most correlated pair: ${maxPair} (r = ${maxC.toFixed(2)})`;
    }

    function tick() {
        if (iter < 220 || draggedNode || hoveredNode !== null) step();
        draw();
        if (iter < 290 || draggedNode || hoveredNode !== null) {
            rafId = requestAnimationFrame(tick);
        } else {
            rafId = null;
        }
    }
    tick();
}



/* ---- 52-week range bar ---- */
function build52wBar(h) {
    if (h.week_52_pct == null) return '<span style="color:var(--text-3)">—</span>';
    const pct = Math.max(0, Math.min(100, h.week_52_pct));
    return `<div class="w52-wrap" title="52w Low: $${h.week_52_low}  |  52w High: $${h.week_52_high}">
        <div class="w52-track"><div class="w52-dot" style="left:${pct}%"></div></div>
        <div class="w52-labels"><span>$${h.week_52_low}</span><span>$${h.week_52_high}</span></div>
    </div>`;
}

/* ---- Sentiment Treemap ---- */
function buildTreemap(holdings) {
    const valid = holdings.filter(h => h.weight_pct > 0).map(h => ({
        t: h.ticker,
        val: h.weight_pct,
        ret: h.annual_return_pct ?? 0,
        w: 0, h: 0, x: 0, y: 0
    })).sort((a,b) => b.val - a.val);

    if (valid.length === 0) return '';

    const W = 460;
    const H = 220;
    const rects = [];

    function sliceAndDice(items, x, y, bw, bh) {
        if (!items.length) return;
        if (items.length === 1) {
            items[0].x = x; items[0].y = y; items[0].w = bw; items[0].h = bh;
            rects.push(items[0]);
            return;
        }
        const total = items.reduce((sum, item) => sum + item.val, 0);
        let run = 0, split = 0;
        for (let i = 0; i < items.length - 1; i++) {
            run += items[i].val;
            split = i;
            if (run >= total / 2) break;
        }
        const left = items.slice(0, split+1);
        const right = items.slice(split+1);
        const lr = left.reduce((s, x) => s + x.val, 0) / total;
        
        if (bw > bh) {
            const wL = bw * lr;
            sliceAndDice(left, x, y, wL, bh);
            sliceAndDice(right, x + wL, y, bw - wL, bh);
        } else {
            const hT = bh * lr;
            sliceAndDice(left, x, y, bw, hT);
            sliceAndDice(right, x, y + hT, bw, bh - hT);
        }
    }
    
    sliceAndDice(valid, 0, 0, W, H);
    
    const boxesHtml = rects.map(r => {
        let color = '#444';
        let txtColor = '#fff';
        if (r.ret > 15) { color = '#ffffff'; txtColor = '#000000'; }
        else if (r.ret > 0) { color = '#aaaaaa'; txtColor = '#000000'; }
        else if (r.ret < -15) { color = '#1a1a1a'; txtColor = '#777777'; }
        else { color = '#444444'; txtColor = '#ffffff'; }

        return `
            <g transform="translate(${r.x}, ${r.y})" style="cursor:help;">
                <title>${r.t}: ${r.val.toFixed(1)}% weight | 1Y: ${r.ret > 0 ? '+' : ''}${r.ret.toFixed(1)}%</title>
                <rect width="${r.w}" height="${r.h}" fill="${color}" stroke="#000" stroke-width="2"></rect>
                ${(r.w > 30 && r.h > 20) ? `<text x="${r.w/2}" y="${r.h/2 - 2}" font-size="${Math.min(18, Math.max(10, r.w/4))}px" font-weight="700" fill="${txtColor}" text-anchor="middle" dominant-baseline="central">${r.t}</text>
                                           <text x="${r.w/2}" y="${r.h/2 + 12}" font-size="${Math.min(11, Math.max(8, r.w/6))}px" font-weight="500" fill="${txtColor}" text-anchor="middle" dominant-baseline="central">${r.ret > 0 ? '+' : ''}${r.ret.toFixed(1)}%</text>` : ''}
            </g>
        `;
    }).join('');

    return `
    <div class="analytics-card" style="margin-bottom:1rem">
        <h3 class="has-tooltip" data-tip="Box size = Portfolio Weight. Color = 1-Year Return.">Performance Treemap</h3>
        <p class="corr-desc">Institutional visualization for exposure attribution. <span style="color:#fff">White = Overperforming</span>, <span style="color:#666">Grey = Underperforming</span>.</p>
        <div style="display:flex; justify-content:center; margin-top: 1rem;">
            <svg width="460" height="220" viewBox="0 0 ${W} ${H}" style="border-radius:var(--radius-sm)">
                ${boxesHtml}
            </svg>
        </div>
    </div>`;
}

/* ---- Stress test ---- */
function buildStressTest(scenarios, portfolioBeta) {
    if (!scenarios || !scenarios.length) return '';
    const cards = scenarios.map(s => `
        <div class="stress-card">
            <div class="stress-scenario">${s.label}</div>
            <div class="stress-pct neg">${s.est_portfolio_pct}%</div>
            <div class="stress-dollar neg">≈ -$${Math.abs(s.est_dollar_impact).toLocaleString()}</div>
        </div>`).join('');

    return `
    <div class="analytics-card">
        <h3 class="has-tooltip" data-tip="${TIPS['Portfolio Beta']}">Stress Test &mdash; Market Downturn Scenarios</h3>
        <p class="corr-desc">Estimated portfolio impact based on portfolio Beta of <strong>${portfolioBeta ?? '?'}</strong>. These are linear estimates; actual losses depend on correlations and market dynamics at the time.</p>
        <div class="stress-grid">${cards}</div>
    </div>`;
}

/* ---- Risk-Return Plot (Alpha Quadrant) ---- */
function buildAlphaQuadrant(holdings) {
    if (!holdings || holdings.length < 2) return '';
    const points = holdings.filter(h => h.annual_volatility_pct != null && h.annual_return_pct != null);
    if (!points.length) return '';

    const W = 460, H = 280;
    const pad = 35;
    
    // Limits
    let minVol = Math.min(0, ...points.map(p => p.annual_volatility_pct));
    let maxVol = Math.max(10, ...points.map(p => p.annual_volatility_pct));
    let minRet = Math.min(0, ...points.map(p => p.annual_return_pct));
    let maxRet = Math.max(10, ...points.map(p => p.annual_return_pct));
    
    maxVol += 5; minVol -= 5;
    maxRet += 5; minRet -= 5;

    const vRange = (maxVol - minVol) || 1;
    const rRange = (maxRet - minRet) || 1;
    
    const getX = vol => pad + ((vol - minVol) / vRange) * (W - pad*2);
    const getY = ret => H - pad - ((ret - minRet) / rRange) * (H - pad*2);
    
    const origX = getX(0); 
    const origY = getY(0);

    const axes = `
        <line x1="${pad}" y1="${origY}" x2="${W-pad}" y2="${origY}" class="ch-zero-line"/>
        <line x1="${origX}" y1="${pad}" x2="${origX}" y2="${H-pad}" class="ch-zero-line"/>
        <text x="${W-pad}" y="${origY-5}" class="ch-axis-lbl" text-anchor="end">Risk (Vol) →</text>
        <text x="${origX+5}" y="${pad}" class="ch-axis-lbl" text-anchor="start">Return (1Y) ↑</text>
    `;

    const dots = points.map(p => {
        const x = getX(p.annual_volatility_pct);
        const y = getY(p.annual_return_pct);
        return `
        <g class="al-node-g">
            <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" class="al-node"/>
            <text x="${x.toFixed(1)}" y="${(y-8).toFixed(1)}" class="al-node-lbl">${p.ticker}</text>
        </g>`;
    }).join('');

    return `
    <div class="analytics-card">
        <h3>The Alpha Quadrant</h3>
        <p class="corr-desc">Risk (Annual Volatility) vs Reward (1Y Return). Ideal position is Top-Left.</p>
        <div style="display:flex;justify-content:center">
            <svg viewBox="0 0 ${W} ${H}" class="alpha-svg" width="100%" height="auto" style="max-width:460px">
                ${axes}
                ${dots}
            </svg>
        </div>
    </div>`;
}

/* ---- Catalyst Radar (Event Sonar) ---- */
function buildEventSonar(holdings) {
    const dates = holdings.filter(h => h.upcoming_earnings).map(h => {
        const parts = h.upcoming_earnings.split('-');
        return {
            ticker: h.ticker, 
            date: new Date(parts[0], parts[1]-1, parts[2])
        };
    }).sort((a, b) => a.date - b.date);
    
    if (!dates.length) return '';

    const now = new Date();
    now.setHours(0,0,0,0);
    
    let items = dates.map(d => {
        const diffTime = d.date - now;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        let dayStr;
        if (diffDays < 0) dayStr = `${Math.abs(diffDays)}d ago`;
        else if (diffDays === 0) dayStr = 'Today';
        else if (diffDays === 1) dayStr = 'Tomorrow';
        else dayStr = `In ${diffDays}d`;

        return `
            <div class="sonar-item">
                <div class="sonar-tick"></div>
                <div class="sonar-meta">
                    <span class="sonar-t">${d.ticker}</span>
                    <span class="sonar-d">${dayStr}</span>
                </div>
            </div>
        `;
    }).join('');

    return `
    <div class="analytics-card">
        <h3>Catalyst Radar</h3>
        <p class="corr-desc">Upcoming earnings and confirmed macro catalysts.</p>
        <div class="sonar-track">
            <div class="sonar-line"></div>
            <div class="sonar-items">${items}</div>
        </div>
    </div>`;
}

function renderAnalytics(data, cont) {
    const m = data.portfolio_metrics || {};
    const div = data.diversification || {};
    const hs = data.holdings || [];
    const total = data.total_value || 0;
    const bmark = data.benchmark_comparison;
    const corr = data.correlation_matrix;
    const stress = data.stress_scenarios || [];
    const portBeta = data.portfolio_beta;

    const retClass = (m.annual_return_pct ?? 0) >= 0 ? 'pos' : 'neg';
    const retSign = (m.annual_return_pct ?? 0) >= 0 ? '+' : '';

    /* ---- Stat cards ---- */
    const statsHtml = `
    <div class="analytics-grid">
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Portfolio Value']}">Portfolio Value</span>
            <span class="stat-value">$${total.toLocaleString('en-US', { maximumFractionDigits: 2 })}</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Annual Return (est.)']}">Annual Return (est.)</span>
            <span class="stat-value ${retClass}">${m.annual_return_pct != null ? retSign + m.annual_return_pct + '%' : '—'}</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Annual Volatility']}">Annual Volatility</span>
            <span class="stat-value">${m.annual_volatility_pct != null ? m.annual_volatility_pct + '%' : '—'}</span>
            <span class="stat-sub">Annualised std-dev</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Sharpe Ratio']}">Sharpe Ratio</span>
            <span class="stat-value ${(m.sharpe_ratio ?? 0) >= 1 ? 'pos' : (m.sharpe_ratio ?? 0) < 0 ? 'neg' : ''}">${m.sharpe_ratio ?? '—'}</span>
            <span class="stat-sub">RF rate 4.5%</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['Portfolio Beta']}">Portfolio Beta</span>
            <span class="stat-value">${portBeta ?? '—'}</span>
            <span class="stat-sub">vs S&amp;P 500</span>
        </div>
        <div class="stat-card">
            <span class="stat-label has-tooltip" data-tip="${TIPS['VaR (1-day, 95%)']}">VaR 1-Day (95%)</span>
            <span class="stat-value neg">${m.var_1d_95 != null ? m.var_1d_95 + '%' : '—'}</span>
            <span class="stat-sub">Max daily loss, 95% conf.</span>
        </div>
    </div>`;

    /* ---- Diversification panel ---- */
    const score = div.score || 0;
    const circ = 2 * Math.PI * 34;
    const filled = (score / 100) * circ;
    const ringColor = score >= 70 ? 'var(--bullish)' : score >= 45 ? 'var(--brand)' : 'var(--bearish)';
    const scoreLabel = score >= 70 ? 'Well Diversified' : score >= 45 ? 'Moderately Diversified' : 'Concentrated';
    const scoreDesc = score >= 70
        ? 'Good spread across sectors and position sizes.'
        : score >= 45
            ? 'Decent spread but notable concentration risks exist.'
            : 'Portfolio is heavily concentrated — significant single-name or sector risk.';

    // Flags as styled chips
    const flagChips = (div.flags || []).map(f =>
        `<div class="div-flag-chip">Alert: ${f}</div>`
    ).join('');

    // Asset class pills
    const assetCls = div.asset_class_breakdown || {};
    const ASSET_COLORS = { Equity: 'var(--text-1)', ETF: 'var(--text-2)', Crypto: 'var(--text-1)', 'Fixed Income': 'var(--text-3)', 'Unknown': 'var(--border)' };
    const assetPills = Object.entries(assetCls).sort((a, b) => b[1] - a[1]).map(([cls, pct]) =>
        `<div class="div-asset-pill" style="border-color:${ASSET_COLORS[cls] || 'var(--border)'}">
            <span class="div-asset-dot" style="background:${ASSET_COLORS[cls] || 'var(--text-3)'}"></span>
            <span>${cls}</span><strong>${Math.round(pct)}%</strong>
        </div>`
    ).join('');

    // Concentration stat — biggest holding
    const biggest = hs.length ? hs.reduce((a, b) => (b.weight_pct || 0) > (a.weight_pct || 0) ? b : a) : null;
    const biggestStr = biggest ? `<div class="div-stat"><span>Largest position</span><strong>${biggest.ticker} — ${biggest.weight_pct}%</strong></div>` : '';
    const sectorCount = Object.keys(div.sector_breakdown || {}).length;

    /* ---- Sector bars ---- */
    const sectors = div.sector_breakdown || {};
    const sectorBars = Object.entries(sectors).sort((a, b) => b[1] - a[1]).map(([s, pct]) => `
        <div class="sector-row">
            <div class="sector-name">${s}</div>
            <div class="sector-bar-bg"><div class="sector-bar-fill" style="width:${pct}%"></div></div>
            <div class="sector-pct">${Math.round(pct)}%</div>
        </div>`).join('');

    /* ---- Holdings table ---- */
    const holdRows = hs.map(h => {
        const pnl = h.gain_loss ?? 0;
        const pnlPct = h.gain_pct ?? 0;
        const pnlCls = pnl >= 0 ? 'pos' : 'neg';
        const sign = pnl >= 0 ? '+' : '';
        const spark = buildSparkline(h.sparkline || []);
        const bar52 = build52wBar(h);
        const betaCls = (h.beta ?? 1) > 1.5 ? 'neg' : (h.beta ?? 1) < 0.6 ? 'pos' : '';
        const peStr = h.pe_ratio != null
            ? `${h.pe_ratio}x<span style="font-size:.68rem;color:var(--text-3);margin-left:2px">${h.pe_type || ''}</span>`
            : '—';
        return `<tr>
            <td><strong>${h.ticker}</strong></td>
            <td class="sparkline-cell">${spark}</td>
            <td>$${h.current_price?.toFixed(2) ?? '—'}</td>
            <td class="w52-cell">${bar52}</td>
            <td>${h.weight_pct ?? '—'}%</td>
            <td class="${pnlCls}">${sign}$${Math.abs(pnl).toFixed(2)}</td>
            <td class="${pnlCls}">${sign}${pnlPct.toFixed(2)}%</td>
            <td>${h.annual_volatility_pct != null ? h.annual_volatility_pct + '%' : '—'}</td>
            <td class="${betaCls}">${h.beta ?? '—'}</td>
            <td>${peStr}</td>
            <td><span style="color:var(--text-2);font-size:.78rem">${h.sector || '—'}</span></td>
        </tr>`;
    }).join('');

    cont.innerHTML = `
        ${statsHtml}
        ${buildBenchmarkChart(bmark)}
        <div class="analytics-row">
            <div class="analytics-card div-card">
                <h3><span class="has-tooltip" data-tip="${TIPS['Diversification Score']}">Diversification</span></h3>
                <div class="div-ring-row">
                    <div class="div-ring">
                        <svg width="88" height="88" viewBox="0 0 88 88">
                            <circle class="div-ring-bg"   cx="44" cy="44" r="34"/>
                            <circle class="div-ring-fill" cx="44" cy="44" r="34" stroke="${ringColor}"
                                stroke-dasharray="${filled} ${circ}"/>
                        </svg>
                        <div class="div-ring-label" style="color:${ringColor}">${score}</div>
                    </div>
                    <div class="div-ring-meta">
                        <div class="div-label" style="color:${ringColor}">${scoreLabel}</div>
                        <div class="div-desc">${scoreDesc}</div>
                        <div class="div-stats">
                            <div class="div-stat"><span>Positions</span><strong>${hs.length}</strong></div>
                            <div class="div-stat"><span>Sectors</span><strong>${sectorCount}</strong></div>
                            ${biggestStr}
                        </div>
                    </div>
                </div>
                <div class="div-assets">${assetPills || '—'}</div>
                ${flagChips ? `<div class="div-flag-list">${flagChips}</div>` : ''}
            </div>
            <div class="analytics-card">
                <h3>Sector Breakdown</h3>
                <div class="sector-bars">${sectorBars || '<p style="color:var(--text-3);font-size:.85rem">—</p>'}</div>
            </div>
        </div>
        <div class="analytics-row">
            ${buildAlphaQuadrant(hs)}
            ${buildEventSonar(hs)}
        </div>
        ${buildStressTest(stress, portBeta)}
        ${buildCorrWeb(corr)}
        ${buildTreemap(hs)}
        <div class="analytics-card" style="margin-bottom:1rem">
            <h3>Holdings Detail</h3>
            <div style="overflow-x:auto">
                <table class="holdings-table">
                    <thead><tr>
                        <th>Ticker</th><th>30d</th><th>Price</th><th>52w Range</th>
                        <th>Weight</th><th>P&amp;L $</th><th>P&amp;L %</th>
                        <th>Volatility</th><th>Beta</th><th>P/E</th><th>Sector</th>
                    </tr></thead>
                    <tbody>${holdRows}</tbody>
                </table>
            </div>
        </div>`;

    // Kick off the correlation physics sim after DOM is written
    if (corr) initCorrSim(corr);
}


/* =====================================================
   ACTION ITEMS
   ===================================================== */
function setupActions() {
    $('refresh-actions-btn').addEventListener('click', loadActions);
}

async function loadActions() {
    const btn = $('refresh-actions-btn');
    const spinner = $('actions-spinner');
    const btnText = btn.querySelector('.btn-text');
    const cont = $('actions-container');

    if (!holdings.length) { alert('Add holdings first.'); switchTab('portfolio'); return; }
    btnText.textContent = 'Analyzing…';
    spinner.classList.remove('hidden');
    btn.disabled = true;
    cont.innerHTML = '<div class="empty-state"><div class="empty-glow"></div><p>Running portfolio analysis…</p></div>';

    try {
        const res = await fetchAuthorized(`${API}/api/actions?_t=${Date.now()}`);
        const data = await res.json();
        renderActions(data.items || [], cont);
    } catch (e) {
        cont.innerHTML = `<div class="empty-state"><p style="color:var(--bearish)">Failed: ${e.message}</p></div>`;
    } finally {
        btnText.textContent = 'Refresh Suggestions';
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
                <div style="display:flex; align-items:center;">
                    <strong>${item.title}</strong>
                    <span class="action-info-icon has-tooltip" data-tip="${item.beginner_tip || ''}">ⓘ</span>
                </div>
                <span class="technical-desc">${item.technical_desc || item.sub || ''}</span>
                ${item.execution_example ? `
                <div class="execution-example">
                    <span class="execution-label">Execution Example</span>
                    <div class="execution-content">${item.execution_example}</div>
                </div>` : ''}
            </div>
        </div>`).join('');

    cont.innerHTML = `
        <div class="actions-panel" style="animation: fadeUp 0.4s ease forwards">
            <h3>Personalized Recommendations</h3>
            <div class="action-items-list">${html}</div>
        </div>`;
}

/* =====================================================
   SNAPTRADE BROKERAGE SYNC
   ===================================================== */
function setupSnapTrade() {
    checkSnapTradeStatus();

    $('snaptrade-connect-btn').addEventListener('click', async () => {
        try {
            const res = await fetchAuthorized(`${API}/api/snaptrade/connect`, { method: 'POST' });
            const data = await res.json();
            if (data.portal_url) {
                const portalWindow = window.open(data.portal_url, '_blank');
                const checkInterval = setInterval(() => {
                    if (portalWindow.closed) {
                        clearInterval(checkInterval);
                        checkSnapTradeStatus();
                    }
                }, 1000);
            }
        } catch (e) { console.error('SnapTrade connect', e); }
    });

    $('snaptrade-sync-btn').addEventListener('click', async () => {
        const btn = $('snaptrade-sync-btn');
        const spinner = $('snaptrade-spinner');
        const btnText = btn.querySelector('.btn-text');
        btnText.textContent = 'Syncing…';
        spinner.classList.remove('hidden');
        btn.disabled = true;

        try {
            const res = await fetchAuthorized(`${API}/api/snaptrade/sync`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                holdings = data.holdings || [];
                renderHoldingsTable();
            }
        } catch (e) { console.error('SnapTrade sync', e); }
        finally {
            btnText.textContent = '↻ Sync Now';
            spinner.classList.add('hidden');
            btn.disabled = false;
        }
    });

    $('snaptrade-disconnect-btn').addEventListener('click', async () => {
        if (!confirm('Are you sure?')) return;
        try {
            await fetchAuthorized(`${API}/api/snaptrade/disconnect`, { method: 'DELETE' });
            checkSnapTradeStatus();
        } catch (e) { console.error('SnapTrade disconnect', e); }
    });
}

async function checkSnapTradeStatus() {
    try {
        const res = await fetchAuthorized(`${API}/api/snaptrade/status`);
        const data = await res.json();
        const discView = $('snaptrade-disconnected-view');
        const connView = $('snaptrade-connected-view');
        const badge = $('snaptrade-status-badge');
        
        if (data.connected) {
            discView.classList.add('hidden');
            connView.classList.remove('hidden');
            badge.textContent = 'Connected';
            badge.className = 'status-badge connected';
            $('st-user-id').textContent = data.snaptrade_user_id || 'Linked';
        } else {
            discView.classList.remove('hidden');
            connView.classList.add('hidden');
            badge.textContent = 'Disconnected';
            badge.className = 'status-badge disconnected';
        }
    } catch (e) { console.error('checkSnapTradeStatus', e); }
}
