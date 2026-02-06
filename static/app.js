/**
 * ANTIGRAVITY INSTITUTIONAL ALGO PLATFORM - CORE LOGIC
 */

const state = {
    isAuth: false,
    selectedMarket: 'NIFTY',
    selectedCommodity: 'GOLD',
    metrics: null,
    trades: [],
    logs: [],
    pnlHistory: [], // Will populate with real-time data
    pnlTimestamps: [], // Corresponding timestamps
    pnlFullTimestamps: [], // Full timestamp strings for tooltips
    chartTimeRange: '1D', // Default time range: 1 Day
    marketBias: {
        'NIFTY': { bias: 'BULLISH', strength: 82 },
        'BANKNIFTY': { bias: 'BEARISH', strength: 65 },
        'SENSEX': { bias: 'BULLISH', strength: 71 },
        'COMMODITY': { bias: 'NEUTRAL', strength: 40 }
    },
    usageLimit: null,
    account_update: null, // Anti-Gravity Account Balance Data
    agentV2Status: {},
    auditTrail: [],
    theme: localStorage.getItem('theme') || 'dark'
};

const agentMetadata = {
    'MarketContext': {
        role: 'Market Context Analyst',
        description: 'Translates raw price action, VWAP, and volume into a high-level directional bias (Bullish/Bearish/Neutral).',
        inputs: 'OHLC, Volume, Reference Closing Price',
        outputs: 'Market Mood, Confidence Score, Analytical Reason'
    },
    'StructurePattern': {
        role: 'Pattern Recognition Agent',
        description: 'Scans for institutional footprints like Break of Structure (BOS) and Change of Character (CHoCH).',
        inputs: 'Live Price (LTP), Historical Price Levels',
        outputs: 'Pattern Type, Price Validation, Trigger Signal'
    },
    'Validation': {
        role: 'Strategic Validator',
        description: 'Decides if a trade setup satisfies all confluence rules before allowing the system to proceed.',
        inputs: 'Market Mood, Detected Patterns, Alignment Rules',
        outputs: 'Execution Permission (True/False), Consensus Reason'
    },
    'RiskCapital': {
        role: 'Risk Management Officer',
        description: 'Enforces strict capital protection rules, calculates lot sizes, and monitors drawdown limits.',
        inputs: 'Portfolio Metrics, Daily P&L, Account Balance',
        outputs: 'Risk Clearance, Calculated Size, Limit Compliance'
    },
    'Execution': {
        role: 'Virtual Execution Engine',
        description: 'Simulates institutional trade execution including fill quality, entry tracking, and P&L calculation.',
        inputs: 'Validator Approval, Risk Clearance, Live Market Price',
        outputs: 'Trade ID, Virtual Fill, Live Ledger Entry'
    },
    'AuditLogger': {
        role: 'Governance & Transparency Agent',
        description: 'Maintains a secure, real-time audit trail of every decision made by the sub-agent network.',
        inputs: 'All Agent Event Bus Messages',
        outputs: 'JSON Decision Audit, Searchable Trace Logs'
    },
    'Guidance': {
        role: 'AI Strategic Advisor',
        description: 'Synthesizes complex analytical data into human-level advice for strategic decision support.',
        inputs: 'Recent Multi-Agent Decisions, Audit Trail',
        outputs: 'Plain-English Advice, Strategic Explanations'
    }
};

let pnlChart = null;

// --- THEME LOGIC ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    state.theme = savedTheme;
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        document.getElementById('theme-icon').textContent = '🌙';
    } else {
        document.body.classList.remove('light-theme');
        document.getElementById('theme-icon').textContent = '☀️';
    }
}

function toggleTheme() {
    if (state.theme === 'dark') {
        state.theme = 'light';
        document.body.classList.add('light-theme');
        localStorage.setItem('theme', 'light');
        document.getElementById('theme-icon').textContent = '🌙';
    } else {
        state.theme = 'dark';
        document.body.classList.remove('light-theme');
        localStorage.setItem('theme', 'dark');
        document.getElementById('theme-icon').textContent = '☀️';
    }
    // Refresh chart to pick up new colors
    if (pnlChart) initAnalytics();
}

// Initialize Theme immediately
window.addEventListener('DOMContentLoaded', initTheme);
window.addEventListener('load', initTheme);

// Market-specific pattern configurations
const MARKET_PATTERNS = {
    'NIFTY': [
        { name: 'EMA 20/50 Crossover', confidence: 'High (84%)', direction: 'LONG', time: '14:45' },
        { name: 'VWAP Pullback Setup', confidence: 'Medium (62%)', direction: 'SHORT', time: '14:30' }
    ],
    'BANKNIFTY': [
        { name: 'Support Bounce', confidence: 'High (78%)', direction: 'LONG', time: '14:50' },
        { name: 'Breakdown Pattern', confidence: 'Low (48%)', direction: 'SHORT', time: '14:15' }
    ],
    'SENSEX': [
        { name: 'Range Consolidation', confidence: 'Medium (55%)', direction: 'LONG', time: '14:25' }
    ],
    'COMMODITY': []
};

// --- NAVIGATION ---
function showTab(el, tabId) {
    document.querySelectorAll('.content-view').forEach(v => v.classList.add('hidden'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    const target = document.getElementById(`tab-${tabId}`);
    if (target) target.classList.remove('hidden');
    if (el) el.classList.add('active');

    if (tabId === 'performance') initAnalytics();
}

function toggleSettingsPanel() {
    const panel = document.getElementById('settings-panel');
    if (panel) panel.classList.toggle('open');
}

// --- AUTHENTICATION FLOW ---

function showAuthPage(page) {
    const cards = ['login', 'register', 'otp', 'forgot'];
    cards.forEach(c => {
        const el = document.getElementById(`card-${c}`);
        if (el) el.classList.add('hidden');
    });

    const target = document.getElementById(`card-${page}`);
    if (target) target.classList.remove('hidden');
}

async function handleLogin() {
    const user_id = document.getElementById('login-id').value.trim();
    const api_key = document.getElementById('login-pass').value;
    const rememberMe = document.getElementById('remember-me').checked;

    // Regex Rules: 
    // 1. User ID: min 4 chars, alphanumeric
    // 2. API Key: min 8 chars
    const idRegex = /^[a-zA-Z0-9_]{4,20}$/;

    if (!user_id || !api_key) {
        return alert("Validation Error: Please enter both User ID and API Key");
    }

    if (!idRegex.test(user_id) && !user_id.includes('@')) {
        return alert("Validation Error: User ID must be 4-20 characters (alphanumeric) or a valid email.");
    }

    if (api_key.length < 5) {
        return alert("Validation Error: API Key/Password must be at least 5 characters.");
    }

    try {
        const res = await fetch('/api/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, api_key })
        });

        const data = await res.json();

        if (res.ok && data.status === 'success') {
            state.isAuth = true;

            // Remember Me Logic
            if (rememberMe) {
                localStorage.setItem('antigravity_user_id', user_id);
            } else {
                localStorage.removeItem('antigravity_user_id');
            }

            document.getElementById('auth-layer').classList.add('hidden');
            document.getElementById('app-layer').classList.remove('hidden');

            // Explicitly ensure side panels are closed on fresh login
            document.getElementById('settings-panel').classList.remove('open');

            // Set mode label if it exists
            const modeEl = document.getElementById('broker-mode-label');
            if (modeEl) {
                modeEl.textContent = `${data.mode} EXECUTION`;
                modeEl.className = data.mode === 'REAL' ? 'badge success' : 'badge warning';
                // Update side indicator too
                const sidebarMode = document.getElementById('broker-mode-sidebar');
                if (sidebarMode) {
                    sidebarMode.textContent = `${data.mode} MODE`;
                    sidebarMode.className = `status-badge ${data.mode === 'REAL' ? 'success' : 'warning'}`;
                }
            }

            initDashboard();
        } else {
            alert("Security Protocol: Access Denied. " + (data.detail || data.reason || "Invalid Credentials Provided."));
        }
    } catch (err) {
        alert("Institutional Network Error: Unable to reach Command Center.");
    }
}

// Auto-populate Remember Me
window.addEventListener('load', () => {
    const savedId = localStorage.getItem('antigravity_user_id');
    if (savedId) {
        document.getElementById('login-id').value = savedId;
        document.getElementById('remember-me').checked = true;
    }
});

async function handleSignup() {
    // Collect registration data
    const name = document.querySelector('#card-register input[placeholder="John Doe"]').value;
    const email = document.querySelector('#card-register input[placeholder="john@example.com"]').value;
    const phone = document.querySelector('#card-register input[placeholder="+91 98765 43210"]').value;
    const password = document.querySelector('#card-register input[type="password"]').value;

    if (!name || !email || !password) {
        return alert("Please fill in all institutional required fields.");
    }

    try {
        const res = await fetch('/api/v1/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, phone, password })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || "OTP Sent Successfully");
            showAuthPage('otp');
            startOTPTimer();
        } else {
            alert("Signup Registration Failed");
        }
    } catch (err) {
        alert("Institutional Setup Connection Error");
    }
}

document.getElementById('btn-register-confirm').onclick = handleSignup;

function startOTPTimer() {
    let timeLeft = 119;
    const timerEl = document.getElementById('otp-timer');
    const timer = setInterval(() => {
        const mins = Math.floor(timeLeft / 60);
        const secs = timeLeft % 60;
        timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        if (timeLeft <= 0) clearInterval(timer);
        timeLeft--;
    }, 1000);
}

function moveOTP(input, next) {
    if (input.value.length === 1 && next <= 6) {
        const nextBox = document.querySelectorAll('.otp-box')[next];
        if (nextBox) nextBox.focus();
    }
}

function validateOTP() {
    const boxes = document.querySelectorAll('.otp-box');
    const otp = Array.from(boxes).map(b => b.value).join('');

    if (otp.length < 6) return alert("Please enter the full 6-digit secure code.");

    // Success simulation
    alert("Identity Verified. Account Activated.");
    showAuthPage('login');
    // Clear boxes
    boxes.forEach(b => b.value = '');
}

async function handleForgotPassword() {
    const email = document.getElementById('forgot-email').value;
    if (!email || !email.includes('@')) {
        return alert("Please enter a valid institution email.");
    }

    try {
        const res = await fetch('/api/v1/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || "Recovery link sent. Check your secure inbox.");
            showAuthPage('login');
        } else {
            alert("Recovery Protocol Failure");
        }
    } catch (err) {
        alert("Global Command Center Connection Error");
    }
}

function logout() {
    state.isAuth = false;
    document.getElementById('app-layer').classList.add('hidden');
    document.getElementById('auth-layer').classList.remove('hidden');
    // Clear sensitive inputs
    document.getElementById('login-pass').value = '';
    console.log("User logged out. Stopping agents.");
}

// --- DASHBOARD LOGIC ---

async function initDashboard() {
    fetchSystemData();
    setInterval(fetchSystemData, 2000);
    initAnalytics();
    updateDetectedPatterns(state.selectedMarket); // Initialize pattern display
    initScrollShadow(); // Setup scroll shadow effect
    setupDashboardEvents();

    // --- ANTI-GRAVITY ACCOUNT UPDATE EVENT LISTENER ---
    window.addEventListener('ACCOUNT_UPDATE', (event) => {
        const data = event.detail;
        if (data && data.balance !== undefined) {
            if (state.metrics) state.metrics.total_capital = data.balance;
            const capEl = document.getElementById('set-total-capital');
            if (capEl && document.activeElement !== capEl) capEl.value = data.balance;
            updateDashboardUI(); // Immediate refresh
        }
    });
}

function setupDashboardEvents() {
    // Market Tabs
    document.querySelectorAll('.market-tab').forEach(tab => {
        tab.onclick = () => {
            document.querySelectorAll('.market-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.selectedMarket = tab.dataset.market;

            // Toggle Commodity selector
            const commWrapper = document.getElementById('commodity-selector-wrapper');
            if (commWrapper) {
                if (state.selectedMarket === 'COMMODITY') {
                    commWrapper.classList.remove('hidden');
                } else {
                    commWrapper.classList.add('hidden');
                }
            }

            updateDetectedPatterns(state.selectedMarket); // Update patterns dynamically
            updateDashboardUI();
        };
    });

    // Commodity Selection
    const commSelect = document.getElementById('commodity-selector');
    if (commSelect) {
        commSelect.onchange = (e) => {
            state.selectedCommodity = e.target.value;
            console.log("Selected Commodity Switched:", state.selectedCommodity);
            updateDashboardUI();
        };
    }

    // Control Buttons
    document.getElementById('main-start').onclick = () => controlSystem('start');
    document.getElementById('main-emergency').onclick = () => controlSystem('square_off_all');
    document.getElementById('main-squareoff').onclick = () => controlSystem('square_off_all');

    // Risk Settings Trigger
    const riskBtn = document.querySelector('#tab-settings .auth-btn');
    if (riskBtn) riskBtn.onclick = saveInstitutionalSettings;
}

async function fetchSystemData() {
    if (!state.isAuth) return;
    try {
        const mRes = await fetch('/api/v1/dashboard/metrics');
        const tRes = await fetch('/api/v1/trades/open');
        const lRes = await fetch('/api/v1/alerts/logs');
        const aRes = await fetch('/api/v1/account/balance');

        if (mRes.ok) state.metrics = await mRes.json();
        if (tRes.ok) state.trades = await tRes.json();
        if (lRes.ok) state.logs = await lRes.json();
        if (aRes.ok) {
            state.account_update = await aRes.json();
            // EMIT SIMULATION: Trigger UI update for balance
            window.dispatchEvent(new CustomEvent('ACCOUNT_UPDATE', { detail: state.account_update }));
        }

        // --- AGENT V2 SYNC ---
        const sRes = await fetch('/api/v1/agents/status');
        const dRes = await fetch('/api/v1/agents/audit');
        if (sRes.ok) state.agentV2Status = await sRes.json();
        if (dRes.ok) state.auditTrail = await dRes.json();

        // Track PnL history for the chart (keep last 50 points, ~100 seconds of data)
        if (state.metrics) {
            const now = new Date();
            const fullTime = now.toLocaleString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, year: 'numeric', month: 'short', day: 'numeric' });
            const compressedTime = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

            state.pnlHistory.push(state.metrics.daily_pnl);
            state.pnlTimestamps.push(compressedTime);
            state.pnlFullTimestamps.push(fullTime);

            // Keep only last 900 data points (~30 minutes at 2s intervals) to prevent memory bloat
            const MAX_HISTORY = 900;
            if (state.pnlHistory.length > MAX_HISTORY) {
                state.pnlHistory.shift();
                state.pnlTimestamps.shift();
                state.pnlFullTimestamps.shift();
            }

            // Update chart if it exists and performance tab is active
            if (pnlChart && !document.getElementById('tab-performance').classList.contains('hidden')) {
                refreshChartData();
            }
        }

        updateDashboardUI();
        updateDetectedPatterns(state.selectedMarket); // Refresh patterns on every sync
        if (state.isAuth) fetchRiskRules();
    } catch (err) { console.error("API Sync Failed"); }
}

async function fetchRiskRules() {
    try {
        const res = await fetch('/api/v1/risk/rules');
        if (res.ok) {
            const rules = await res.json();
            document.getElementById('rule-max-trades').textContent = rules.max_trades_per_day;
            document.getElementById('rule-risk-trade').textContent = `${rules.risk_per_trade_percent}%`;
            document.getElementById('rule-max-loss').textContent = `${rules.max_daily_loss_percent}%`;
        }
    } catch (err) { console.error("Risk Rule Sync Failed"); }
}

function handleCapitalChange(val) {
    const customInput = document.getElementById('custom-capital-input');
    if (val === 'custom') {
        customInput.classList.remove('hidden');
    } else {
        customInput.classList.add('hidden');
        applyCapitalPreset(val);
    }
}

async function applyCapitalPreset(amount) {
    try {
        const res = await fetch('/api/v1/settings/capital', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: parseFloat(amount) })
        });
        if (res.ok) {
            console.log("Capital Allocation Updated:", amount);
            fetchSystemData();
        }
    } catch (err) { console.error("Capital Update Failed"); }
}

// 1. Market Header & Context Flow Logic
async function updateMarketHeader() {
    if (!state.metrics) return;

    try {
        const r = await fetch(`/api/v1/market/ohlc/${state.selectedMarket}`);
        const response = await r.json();

        const container = document.getElementById('dynamic-price-container');
        if (!container) return;

        if (response.status === 'MARKET_CLOSED') {
            container.innerHTML = `<div class="status-pill blocked">Market Closed — Live feed stopped safely</div>`;
            return;
        }

        if (response.status === 'success') {
            let dataItems = Array.isArray(response.data) ? response.data : [response];

            // --- COMMODITY FILTERING ---
            if (state.selectedMarket === 'COMMODITY') {
                dataItems = dataItems.filter(item => item.instrument === state.selectedCommodity);
            }

            // Clear and rebuild if item count changed
            const existingBoxes = container.querySelectorAll('.price-box');
            if (existingBoxes.length !== dataItems.length) {
                container.innerHTML = '';
            }

            dataItems.forEach((item, index) => {
                let box = container.querySelectorAll('.price-box')[index];
                if (!box) {
                    box = document.createElement('div');
                    box.className = 'metric-item price-box';
                    box.innerHTML = `
                        <span class="label"></span>
                        <span class="val huge"></span>
                        <span class="change"></span>
                    `;
                    container.appendChild(box);
                }

                const labelEl = box.querySelector('.label');
                const ltpEl = box.querySelector('.val');
                const chgEl = box.querySelector('.change');

                const symbol = item.instrument || state.selectedMarket;
                const ltp = item.ltp || 0;
                const close = item.close || ltp || 1.0;
                const change = ltp - close;
                const pct = (close > 0) ? (change / close * 100).toFixed(2) : "0.00";

                labelEl.textContent = symbol;
                ltpEl.textContent = ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 });
                chgEl.textContent = `${change >= 0 ? '+' : ''}${pct}%`;

                chgEl.style.color = change >= 0 ? 'var(--success)' : 'var(--danger)';
                chgEl.style.background = change >= 0 ? 'rgba(0,255,157,0.1)' : 'rgba(255,62,62,0.1)';
                ltpEl.style.color = change >= 0 ? 'var(--success)' : 'var(--danger)';

            });
        }
    } catch (e) { console.error("Market Feed Error:", e); }
}

// --- CAPITAL MANAGEMENT LOGIC ---
function updateCapitalSettings() {
    const capSelect = document.getElementById('select-total-cap');
    const usedInput = document.getElementById('input-used-cap-limit');

    // Total Capital Handling
    if (capSelect.value === 'custom') {
        const customVal = prompt("Enter Custom Capital Amount (₹):");
        if (customVal && !isNaN(customVal)) {
            state.metrics.total_capital = parseFloat(customVal);
        }
    } else {
        state.metrics.total_capital = parseFloat(capSelect.value);
    }

    // Usage Limit Handling
    const limitVal = parseFloat(usedInput.value);
    if (!isNaN(limitVal) && limitVal > 0) {
        state.usageLimit = limitVal;
    } else {
        state.usageLimit = null; // No limit
    }

    updateDashboardUI();
}

function updateDashboardUI() {
    if (!state.metrics) return;

    // 1. Top Metrics & Capital Logic
    updateMarketHeader(); // Trigger async header update

    // Bias
    const biasEl = document.getElementById('mkt-bias');
    const labelEl = document.getElementById('mkt-symbol-label');
    if (labelEl) labelEl.textContent = state.selectedMarket;

    if (biasEl) {
        // Use global or selected market bias
        const bias = state.marketBias[state.selectedMarket]?.bias || 'NEUTRAL';
        biasEl.textContent = bias;
        biasEl.className = `val ${bias === 'BULLISH' ? 'success-text' : (bias === 'BEARISH' ? 'danger-text' : 'text-dim')}`;
    }

    // Capital
    const usedActual = state.metrics.used_capital_amount;
    const total = state.metrics.total_capital;
    const limit = state.usageLimit;

    // Logic: If user sets a limit (Allocated), show that as the numerator.
    // User Request: "50000/100000" -> Limit / Total
    const displayNumerator = (limit && limit > 0) ? limit : usedActual;

    // Helper: Safe number formatter (prevents NaN display)
    const safeNumber = (val, fallback = '—') => {
        if (val === null || val === undefined || isNaN(val) || !isFinite(val)) {
            return fallback;
        }
        return val.toLocaleString();
    };

    document.getElementById('hud-used-cap').textContent = `₹${safeNumber(displayNumerator)} / ₹${safeNumber(total)}`;

    // Calc Available (Free to allocate)
    const available = total - displayNumerator;
    const availLabel = document.querySelector('#hud-used-cap + .card-sub');
    if (availLabel) availLabel.textContent = `Available: ₹${safeNumber(available)}`;


    // 2. KPI Cards (with NaN protection)
    const dailyPnl = state.metrics.daily_pnl;
    const hudProfit = document.getElementById('hud-profit');
    if (dailyPnl !== null && dailyPnl !== undefined && !isNaN(dailyPnl)) {
        hudProfit.textContent = `₹${safeNumber(dailyPnl)}`;
        hudProfit.className = `card-val ${dailyPnl >= 0 ? 'success-text' : 'danger-text'}`;
    } else {
        hudProfit.textContent = '—';
        hudProfit.className = 'card-val';
    }

    const maxDrawdown = state.metrics.max_drawdown;
    const hudDrawdown = document.getElementById('hud-drawdown');
    if (maxDrawdown !== null && maxDrawdown !== undefined && !isNaN(maxDrawdown)) {
        hudDrawdown.textContent = `₹${safeNumber(Math.abs(maxDrawdown))}`;
    } else {
        hudDrawdown.textContent = '—';
    }

    // Risk Meter (with validation)
    const riskMeter = document.getElementById('hud-risk-meter');
    const riskPercent = state.metrics.risk_used_percent;
    if (riskPercent !== null && riskPercent !== undefined && !isNaN(riskPercent)) {
        riskMeter.textContent = `${safeNumber(riskPercent)}%`;
        riskMeter.className = `card-val ${riskPercent > 80 ? 'danger-text' : ''}`;
    } else {
        riskMeter.textContent = '—';
        riskMeter.className = 'card-val';
    }

    // 2. Agent Intelligence & Explainability
    updateAgentExplainabilityPanel();

    // Filtered trades for context-aware summaries
    const MARKET_SYMBOLS = {
        'NIFTY': ['NIFTY'],
        'BANKNIFTY': ['BANKNIFTY'],
        'SENSEX': ['SENSEX'],
        'COMMODITY': ['CRUDEOIL', 'GOLD', 'SILVER', 'NATGASMINI']
    };

    const relevantSymbols = (state.selectedMarket === 'COMMODITY')
        ? [state.selectedCommodity]
        : (MARKET_SYMBOLS[state.selectedMarket] || [state.selectedMarket]);

    const filteredTrades = state.trades.filter(t => relevantSymbols.some(s => t.instrument.includes(s)));

    // Header PnL & Points Summary (Safe checks for missing elements)
    const marketPnL = filteredTrades.reduce((acc, t) => acc + t.pnl, 0);
    const pnlSumEl = document.getElementById('sys-pnl-summary');
    if (pnlSumEl) {
        pnlSumEl.textContent = `${marketPnL >= 0 ? '+' : ''}₹${marketPnL.toLocaleString()}`;
        pnlSumEl.className = `val ${marketPnL >= 0 ? 'success-text' : 'danger-text'}`;
    }

    const marketPoints = filteredTrades.reduce((acc, t) => {
        const p = (t.current_price - t.entry_price) * (t.direction === 'LONG' ? 1 : -1);
        return acc + p;
    }, 0);
    const pointsSumEl = document.getElementById('sys-points-summary');
    if (pointsSumEl) {
        pointsSumEl.textContent = `${marketPoints >= 0 ? '+' : ''}${marketPoints.toFixed(1)} pts`;
        pointsSumEl.className = `val ${marketPoints >= 0 ? 'success-text' : 'danger-text'}`;
    }

    const marketExposure = filteredTrades.reduce((acc, t) => acc + (t.entry_price * t.quantity), 0);
    const exposureEl = document.getElementById('sys-exposure-summary');
    if (exposureEl) exposureEl.textContent = `₹${marketExposure.toLocaleString()}`;

    // Update Commodity Status Pill
    const commStatusPill = document.getElementById('commodity-status-pill');
    if (commStatusPill) {
        if (state.selectedMarket === 'COMMODITY') {
            commStatusPill.classList.remove('hidden');
            const hasPosition = filteredTrades.length > 0;
            commStatusPill.className = `status-pill ${hasPosition ? 'active' : 'idle'}`;
            const statusText = document.getElementById('commodity-status-text');
            if (statusText) statusText.textContent = `${state.selectedCommodity}: ${hasPosition ? 'ACTIVE' : 'IDLE'}`;
        } else {
            commStatusPill.classList.add('hidden');
        }
    }

    // 3. Agents V2 Status
    const agentContainer = document.getElementById('agents-v2-container');
    if (agentContainer && state.agentV2Status) {
        agentContainer.innerHTML = Object.entries(state.agentV2Status).map(([name, status]) => `
            <div class="status-row">
                <span class="agent-name">${name}</span>
                <span class="agent-badge status-${status.toLowerCase()}">${status}</span>
            </div>
        `).join('');
    }

    // 4. Signal Intelligence Panel
    const lastSignal = [...state.auditTrail].reverse().find(e => e.agent === 'StructurePatternAgent' && e.symbol === state.selectedMarket);
    const lastContext = [...state.auditTrail].reverse().find(e => e.agent === 'MarketContextAgent' && e.symbol === state.selectedMarket);

    if (lastContext) {
        const trendEl = document.getElementById('intel-trend');
        if (trendEl) {
            const mood = lastContext.payload.market_mood;
            trendEl.textContent = mood.toUpperCase();
            trendEl.className = `val ${mood.toLowerCase()}`;
        }
    }

    if (lastSignal) {
        const patEl = document.getElementById('intel-pattern');
        const confEl = document.getElementById('intel-confidence');
        const reasonEl = document.getElementById('intel-reason');

        if (patEl) patEl.textContent = lastSignal.payload.pattern;
        if (confEl) confEl.textContent = `${(lastSignal.confidence * 100).toFixed(0)}%`;

        // Find reason from either context or pattern
        const reason = lastSignal.payload.pattern !== 'None' ? `Detected ${lastSignal.payload.pattern} at ${lastSignal.payload.price_level}` : (lastContext ? lastContext.payload.reason : "");
        if (reasonEl) reasonEl.textContent = reason;
    }

    // 5. ChatGPT Guidance Advisor
    const lastAdvice = [...state.auditTrail].reverse().find(e => e.agent === 'GuidanceAgent');
    const adviceEl = document.getElementById('ai-guidance-text');
    if (adviceEl && lastAdvice) {
        adviceEl.textContent = lastAdvice.payload.advice;
    }

    // 6. Decision Audit Trail
    const auditContainer = document.getElementById('v2-audit-trail');
    if (auditContainer && state.auditTrail.length > 0) {
        const relevantAudit = state.auditTrail.slice(-20).reverse();
        auditContainer.innerHTML = relevantAudit.map(e => `
            <div class="audit-row">
                <span class="time">${e.timestamp.split('T')[1].split('.')[0]}</span>
                <span class="agent">${e.agent}</span>
                <span class="data">${JSON.stringify(e.payload)}</span>
                <span class="conf">${(e.confidence * 100).toFixed(0)}%</span>
            </div>
        `).join('');
    }


    // 4. Detected Patterns - Handled by reactive updateDetectedPatterns(state.selectedMarket)
    // Removed static override to allow symbol-specific patterns to show

    // 5. Positions
    const tableBody = document.getElementById('v3-positions-body');

    if (filteredTrades.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" class="empty-msg">No active exposure in ${state.selectedMarket}</td></tr>`;
    } else {
        tableBody.innerHTML = filteredTrades.map(t => `
            <tr>
                <td>
                    <div class="symbol-cell" style="cursor: pointer; position: relative;" onclick="navigateToMarketDetail('${t.instrument}')">
                        <span class="name">${t.instrument}</span>
                        <span class="tag">${t.id}</span>
                        <span style="font-size: 0.6rem; color: var(--accent); position: absolute; right: 0; bottom: 0;">DETAILS →</span>
                    </div>
                </td>
                <td><span class="success-text" style="font-weight: 800;">${t.direction}</span></td>
                <td>${t.lots} Lots <span class="subtitle">(${t.quantity} Qty)</span></td>
                <td>${t.entry_price.toFixed(2)} → ${t.current_price.toFixed(2)}</td>
                <td><span class="points-captured">${((t.current_price - t.entry_price) * (t.direction === 'LONG' ? 1 : -1)).toFixed(1)} pts</span></td>
                <td class="accent-text">12.5%</td>
                <td style="text-align: right;" class="bold success-text">₹${t.pnl.toLocaleString()}</td>
            </tr>
        `).join('');
    }

    // 6. Terminal
    if (state.logs.length > 0) {
        const terminalEl = document.getElementById('v3-terminal');
        const latestLogs = state.logs.slice(-20).reverse();
        terminalEl.innerHTML = latestLogs.map(l => `
            <div class="t-row">
                <span class="t-time">${l.timestamp.split('T')[1]?.split('.')[0] || ''}</span>
                <span class="t-msg ${l.message.includes('Order') ? 'trade' : (l.message.includes('REJECTED') ? 'error' : '')}">${l.message}</span>
            </div>
        `).join('');
    }

    // 7. Analytics Reconciliation (Closed Trades)
    const reconBody = document.getElementById('recon-body');
    if (reconBody) {
        const closed = state.trades.filter(t => t.status === 'CLOSED');
        if (closed.length === 0) {
            reconBody.innerHTML = `<tr><td colspan="7" class="empty-msg">No closed sessions for today</td></tr>`;
        } else {
            reconBody.innerHTML = closed.map(t => `
                <tr>
                    <td>${t.timestamp.split('T')[1].split('.')[0]}</td>
                    <td>${t.instrument}</td>
                    <td><span class="badge">${t.direction}</span></td>
                    <td>${t.entry_price.toFixed(2)}</td>
                    <td>${t.current_price.toFixed(2)}</td>
                    <td>${((t.current_price - t.entry_price) * (t.direction === 'LONG' ? 1 : -1)).toFixed(1)}</td>
                    <td style="text-align: right;" class="${t.pnl >= 0 ? 'success-text' : 'danger-text'}">₹${t.pnl.toLocaleString()}</td>
                </tr>
            `).join('');
        }
    }
}

function updateAgentExplainabilityPanel() {
    const container = document.getElementById('agent-explain-grid');
    if (!container || !state.agentV2Status) return;

    const agents = Object.entries(state.agentV2Status);
    container.innerHTML = agents.map(([name, status]) => {
        const meta = agentMetadata[name] || { role: 'Core Agent', description: 'Institutional Processing Unit' };

        // Find last decision for this agent
        const lastEvent = [...state.auditTrail].reverse().find(e => e.agent.includes(name));
        const timestamp = lastEvent ? lastEvent.timestamp.split('T')[1].split('.')[0] : '--:--:--';
        const task = lastEvent ? (lastEvent.payload.reason || lastEvent.payload.advice || 'Processing market data...') : 'Awaiting data cycle...';

        return `
            <div class="agent-card-interactive" onclick="showAgentDetails('${name}')">
                <div class="card-header">
                    <h4>${name.toUpperCase()}</h4>
                    <span class="status-pill status-${status.toLowerCase()}">${status}</span>
                </div>
                <div class="context-line">${meta.role}</div>
                <div class="task-snapshot">${task}</div>
                <div style="font-size: 0.6rem; color: var(--text-dim); margin-top: 12px;">Last Update: ${timestamp}</div>
            </div>
        `;
    }).join('');
}

function toggleAgentDrawer(open) {
    const drawer = document.getElementById('agent-detail-drawer');
    if (drawer) {
        if (open) drawer.classList.add('open');
        else drawer.classList.remove('open');
    }
}

function showAgentDetails(agentName) {
    const meta = agentMetadata[agentName];
    if (!meta) return;

    document.getElementById('drawer-agent-name').textContent = agentName.replace(/Agent$/, '');
    document.getElementById('drawer-responsibility').textContent = meta.description;

    const status = state.agentV2Status[agentName] || 'IDLE';
    const statusTag = document.getElementById('drawer-agent-status-tag');
    statusTag.textContent = status;
    statusTag.className = `status-pill status-${status.toLowerCase()}`;

    // Find last event for decisions
    const lastEvent = [...state.auditTrail].reverse().find(e => e.agent.includes(agentName));

    if (lastEvent) {
        document.getElementById('drawer-current-task').textContent = lastEvent.payload.reason || lastEvent.payload.advice || 'Actively monitoring selected market triggers.';

        // Snapshot
        const payload = lastEvent.payload;
        let signal = 'NEUTRAL';
        if (payload.pattern && payload.pattern !== 'None') signal = payload.pattern;
        if (payload.market_mood) signal = payload.market_mood;
        if (payload.entry_allowed !== undefined) signal = payload.entry_allowed ? 'ALLOWED' : 'BLOCKED';
        if (payload.trade_id) signal = 'EXECUTED';

        document.getElementById('snapshot-signal').textContent = signal;
        document.getElementById('snapshot-reason').textContent = payload.reason || payload.advice || 'Confluance scan completed.';
        document.getElementById('snapshot-time').textContent = lastEvent.timestamp.split('T')[1].split('.')[0];
    } else {
        document.getElementById('drawer-current-task').textContent = 'Waiting for next market execution cycle.';
        document.getElementById('snapshot-signal').textContent = '--';
        document.getElementById('snapshot-reason').textContent = 'N/A';
        document.getElementById('snapshot-time').textContent = '--:--:--';
    }

    toggleAgentDrawer(true);
}

async function requestAiAdvice() {
    const adviceEl = document.getElementById('ai-guidance-text');
    if (!adviceEl) return;

    const originalText = adviceEl.textContent;
    adviceEl.textContent = "🧠 AI is analyzing institutional context... please wait.";
    adviceEl.style.opacity = "0.7";

    try {
        const res = await fetch('/api/v1/agents/guidance/on-demand', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'success') {
            adviceEl.textContent = data.advice;
            adviceEl.style.opacity = "1";
        } else {
            adviceEl.textContent = "Strategic Link Failure. Try again.";
            adviceEl.style.opacity = "1";
        }
    } catch (err) {
        adviceEl.textContent = "Signal Interference. Check backend connection.";
        adviceEl.style.opacity = "1";
    }
}

function navigateToMarketDetail(symbol) {
    const sym = symbol || state.selectedMarket;
    const titleEl = document.getElementById('detail-market-title');
    if (titleEl) titleEl.innerHTML = `${sym} <span style="font-weight: 300; opacity: 0.5;">FUTURES</span>`;

    // Dynamic Specs
    const lotSizes = { 'NIFTY': '50', 'BANKNIFTY': '25', 'COMMODITY': '100', 'SENSEX': '10' };
    const lotEl = document.getElementById('detail-lot-size');
    if (lotEl) lotEl.textContent = `${lotSizes[sym] || '50'} units (1x)`;

    showTab(null, 'market-detail');
}

function navigateToAgentDetail(name) {
    const titleEl = document.getElementById('detail-agent-title');
    if (titleEl) titleEl.innerHTML = `${name.toUpperCase()} <span style="font-weight: 300; opacity: 0.5;">CORE LOGIC</span>`;
    showTab(null, 'agent-detail');
}

// --- SYSTEM CONTROLS ---
function setExecutionMode(mode) {
    // 1. Update UI
    document.querySelectorAll('.mode-option').forEach(el => el.classList.remove('selected'));
    const target = document.getElementById(mode === 'AUTO' ? 'mode-auto' : 'mode-manual');
    if (target) target.classList.add('selected');

    // 2. Alert User (Mock Backend Call)
    console.log(`Execution Mode Switched to: ${mode}`);
    // await fetch('/api/v1/settings/mode', ... ); 

    const label = document.getElementById('broker-mode-label');
    if (label) label.textContent = `${mode} EXECUTION`;
}

async function controlSystem(action) {
    if (action === 'reset') {
        if (!confirm("⚠️ SYSTEM RESET\n\nThis will clear strictly local session logs and chart history. Continue?")) return;
        // Mock Reset
        state.logs = [];
        state.pnlHistory = [];
        // fetchSystemData() will effectively reload state
        alert("Session Reset Initiated.");
        window.location.reload();
        return;
    }

    const route = action === 'start' ? 'system/start' :
        (action === 'square_off_all' ? 'system/square_off_all' : 'system/pause');

    await fetch(`/api/v1/${route}`, { method: 'POST' });
    fetchSystemData();
}


function getComputedColor(varName) {
    return getComputedStyle(document.body).getPropertyValue(varName).trim();
}

function initAnalytics() {
    const ctx = document.getElementById('pnlChart').getContext('2d');
    if (pnlChart) pnlChart.destroy();

    const { labels, data, fullTimestamps } = getFilteredChartData();

    // Theme Colors
    const primary = getComputedColor('--primary');
    const textDim = getComputedColor('--text-dim');
    const border = getComputedColor('--border');
    const glow = getComputedColor('--primary-glow');

    // Adjust colors for background/grid based on theme state
    const isLight = state.theme === 'light';
    const gridColor = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';
    const tooltipBg = isLight ? 'rgba(255,255,255,0.95)' : 'rgba(10, 14, 26, 0.95)';
    const tooltipText = isLight ? '#000' : '#fff';

    pnlChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels.length > 0 ? labels : ['Awaiting data...'],
            datasets: [{
                label: 'Intraday PnL (₹)',
                data: data,
                borderColor: primary,
                backgroundColor: glow, // Uses the variable now
                borderWidth: 2,
                tension: 0.3,
                fill: true,
                pointRadius: (context) => (labels.length > 100 ? 0 : 3), // Hide points if too many
                pointHoverRadius: 6,
                pointBackgroundColor: primary,
                pointBorderColor: isLight ? '#fff' : '#000',
                pointBorderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    backgroundColor: tooltipBg,
                    titleColor: primary,
                    bodyColor: tooltipText,
                    borderColor: primary,
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        title: (context) => fullTimestamps[context[0].dataIndex] || 'N/A',
                        label: (context) => `PnL: ₹${context.parsed.y.toLocaleString()}`
                    }
                }
            },
            scales: {
                y: {
                    grid: { color: gridColor },
                    ticks: {
                        color: textDim,
                        font: { size: 10 },
                        callback: (value) => '₹' + value.toLocaleString()
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        color: textDim,
                        font: { size: 10 },
                        maxRotation: 0,
                        minRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 12
                    }
                }
            }
        }
    });

    updateChartContainerWidth(labels.length);
}

function updateChartContainerWidth(pointCount) {
    const container = document.querySelector('.chart-canvas-container');
    const wrapper = document.querySelector('.chart-scroll-wrapper');
    if (!container || !wrapper) return;

    const minWidthPerPoint = 15; // px per data point
    const minTotalWidth = wrapper.clientWidth;
    const calculatedWidth = pointCount * minWidthPerPoint;

    if (calculatedWidth > minTotalWidth) {
        container.style.width = calculatedWidth + 'px';
        // Auto-scroll to end on new data
        if (state.chartTimeRange === '1D') {
            wrapper.scrollLeft = calculatedWidth;
        }
    } else {
        container.style.width = '100%';
    }
}


async function saveInstitutionalSettings() {
    const config = {
        total_capital: parseFloat(document.getElementById('set-total-capital').value),
        max_daily_loss_percent: parseFloat(document.getElementById('set-max-loss').value),
        risk_per_trade_percent: parseFloat(document.getElementById('set-risk-trade').value),
        max_trades_per_day: parseInt(document.getElementById('set-max-trades').value)
    };

    try {
        const res = await fetch('/api/v1/settings/risk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (res.ok) {
            alert("Strategic Risk Protocols Updated Successfully");
            fetchSystemData();
        } else {
            const errData = await res.json();
            alert("Risk Protocol Rejection: " + (errData.detail || "Invalid Parameters"));
        }
    } catch (err) {
        alert("Global Command Center: Connectivity Failure");
    }
}







function setUsageLimit(val) {
    if (!val) return;
    state.usageLimit = parseFloat(val);
    alert(`Deployment Limit Set: ₹${state.usageLimit.toLocaleString()}`);
    updateDashboardUI();
}

// --- CHART TIME RANGE FILTERING ---
function setChartTimeRange(range) {
    state.chartTimeRange = range;
    document.querySelectorAll('.time-range-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelector(`[data-range="${range}"]`).classList.add('active');
    if (pnlChart) refreshChartData();
}

function refreshChart() {
    if (pnlChart) refreshChartData();
}
function refreshChartData() {
    const { labels, data, fullTimestamps } = getFilteredChartData();
    pnlChart.data.labels = labels;
    pnlChart.data.datasets[0].data = data;
    pnlChart.options.plugins.tooltip.callbacks.title = (context) => fullTimestamps[context[0].dataIndex] || '';
    pnlChart.update('none'); // Update without animation for smoother live feed
    updateChartContainerWidth(labels.length);
}

function getFilteredChartData() {
    const rangeConfig = {
        '1D': { points: 500, step: 1 },
        '5D': { points: 1500, step: 2 },
        '1M': { points: 3000, step: 5 },
        '3M': { points: 5000, step: 10 },
        '6M': { points: 8000, step: 20 },
        '1Y': { points: 12000, step: 50 }
    };

    const cfg = rangeConfig[state.chartTimeRange] || rangeConfig['1D'];
    const limit = cfg.points;
    const step = cfg.step;

    let history = state.pnlHistory;
    let timestamps = state.pnlTimestamps;
    let fullTs = state.pnlFullTimestamps;

    // Simulate historical data if history is too short for long ranges
    if (history.length < 50 && state.chartTimeRange !== '1D') {
        return mockHistoricalData(state.chartTimeRange);
    }

    const startIdx = Math.max(0, history.length - limit);
    let slicedData = history.slice(startIdx);
    let slicedTimestamps = timestamps.slice(startIdx);
    let slicedFullTimestamps = fullTs.slice(startIdx);

    // Apply Downsampling (Dynamic Compression)
    if (step > 1) {
        slicedData = slicedData.filter((_, i) => i % step === 0);
        slicedTimestamps = slicedTimestamps.filter((_, i) => i % step === 0);
        slicedFullTimestamps = slicedFullTimestamps.filter((_, i) => i % step === 0);
    }

    return { labels: slicedTimestamps, data: slicedData, fullTimestamps: slicedFullTimestamps };
}

function mockHistoricalData(range) {
    // Generate some fake data to show the layout even with no history
    const pointsCount = 100;
    const data = [];
    const labels = [];
    const fullTs = [];
    let base = 500;
    const now = new Date();

    for (let i = 0; i < pointsCount; i++) {
        base += (Math.random() - 0.45) * 50;
        data.push(base);
        const d = new Date(now.getTime() - (pointsCount - i) * 3600000); // 1h intervals
        labels.push(d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        fullTs.push(d.toLocaleString());
    }
    return { labels, data, fullTimestamps: fullTs };
}

// --- DYNAMIC PATTERN DETECTION ---
function updateDetectedPatterns(market) {
    const patterns = MARKET_PATTERNS[market] || [];
    const container = document.getElementById('detected-patterns');
    if (!container) return;
    if (patterns.length === 0) {
        container.innerHTML = `<div class="empty-msg">No active patterns detected for ${market}</div>`;
        return;
    }
    container.innerHTML = patterns.map(p => `<div class="pattern-card" data-direction="${p.direction}">
            <div class="pattern-header">
                <span class="pattern-name">${p.name}</span>
                <span class="pattern-direction ${p.direction.toLowerCase()}">${p.direction}</span>
            </div>
            <div class="pattern-meta">
                <span class="confidence">${p.confidence}</span>
                <span class="time-detected">Detected at ${p.time} IST</span>
            </div>
            <button class="auth-link" style="font-size: 0.6rem; margin-top: 8px; justify-content: flex-end;" onclick="navigateToAgentDetail('Market Context')">VIEW REASONING →</button>
        </div>`).join('');
}

// --- SCROLL SHADOW EFFECT ---
function initScrollShadow() {
    const mainContent = document.querySelector('.main-content-v2');
    const header = document.querySelector('.market-selector');
    if (!mainContent || !header) return;
    mainContent.addEventListener('scroll', () => {
        if (mainContent.scrollTop > 10) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    });
}

// --- DEFAULT MARKET PREFERENCE HANDLER ---
function updateDefaultMarket() {
    const dropdown = document.getElementById('default-market-select');
    if (!dropdown) return;

    const newMarket = dropdown.value;

    // Update state
    state.selectedMarket = newMarket;

    // Update active tab visually
    document.querySelectorAll('.market-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.market === newMarket) {
            tab.classList.add('active');
        }
    });

    // Refresh dashboard UI with new market
    updateDetectedPatterns(newMarket);
    updateDashboardUI();

    // Automatically switch to Main Dashboard to show the change
    showTab(null, 'dashboard');

    // Update the active nav button
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.includes('Main Dashboard')) {
            btn.classList.add('active');
        }
    });

    // User feedback
    alert(`✓ Default market changed to ${newMarket}\nDashboard updated and refreshed!`);

    console.log(`✓ Default market updated to: ${newMarket}. Dashboard refreshed.`);
}

// Initialize default market dropdown on load
window.addEventListener('load', () => {
    const dropdown = document.getElementById('default-market-select');
    if (dropdown) {
        dropdown.value = state.selectedMarket;
    }
});