const PROXY = "http://127.0.0.1:8000";
const REFRESH_MS = 5000;

const els = {
  connDot: document.getElementById("connDot"),
  connText: document.getElementById("connText"),
  spentToday: document.getElementById("spentToday"),
  totalRequests: document.getElementById("totalRequests"),
  totalCost: document.getElementById("totalCost"),
  budgets: document.getElementById("budgets"),
  models: document.getElementById("models"),
  ledgerBody: document.getElementById("ledgerBody"),
  footerUrl: document.getElementById("footerUrl"),
  footerInterval: document.getElementById("footerInterval"),
  optionsLink: document.getElementById("optionsLink"),
};

let timerId = null;

function setConn(ok, text) {
  els.connDot.className = ok ? "dot ok" : "dot err";
  els.connText.textContent = text;
}

async function jsonFetch(path) {
  const res = await fetch(`${PROXY}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status} ${path}`);
  }
  return res.json();
}

function fmtMoney(n) {
  return (n || 0).toFixed(4);
}

function fmtCount(n) {
  return Number(n || 0).toLocaleString();
}

function statusChip(status) {
  const map = {
    forwarded: "forwarded",
    blocked: "blocked",
    failed: "failed",
    pending: "pending",
  };
  return `<span class="chip ${map[status] || "pending"}">${status}</span>`;
}

function renderBudgets(keys) {
  if (!keys || !keys.length) {
    els.budgets.innerHTML = '<div class="empty">No keys seen yet.</div>';
    return;
  }
  els.budgets.innerHTML = keys
    .map(
      (k) => `
      <div class="budget-card">
        <div class="budget-top">
          <div>
            <div class="budget-name" title="${k.label}">${k.label}</div>
            <div class="budget-key">key ${k.key_hash_prefix}</div>
          </div>
          <div class="budget-amount">$${fmtMoney(k.spent_today_usd)} / $${fmtMoney(k.daily_limit_usd)}</div>
        </div>
        <div class="budget-bar"><div class="budget-fill ${k.hard_block ? "" : "warn"}" style="width:${
          k.daily_limit_usd ? Math.min(100, (k.spent_today_usd / k.daily_limit_usd) * 100) : 0
        }%"></div></div>
        <div style="color:var(--muted);font-size:11px;margin-top:6px">
          ${k.requests} requests · last ${k.last_activity ? new Date(k.last_activity).toLocaleTimeString() : "—"}
        </div>
      </div>`
    )
    .join("");
}

function renderModels(models) {
  if (!models || !models.length) {
    els.models.innerHTML = '<div class="empty">No spend data yet.</div>';
    return;
  }
  els.models.innerHTML = models
    .map(
      (m) => `
      <div class="model-row">
        <div class="model-name" title="${m.model}">${m.model}</div>
        <div class="model-meta">${fmtCount(m.requests)} req · $${fmtMoney(m.estimated_cost_usd)} est</div>
      </div>`
    )
    .join("");
}

function renderLedger(entries) {
  if (!entries || !entries.length) {
    els.ledgerBody.innerHTML = '<tr><td colspan="5" class="empty">No activity yet.</td></tr>';
    return;
  }
  els.ledgerBody.innerHTML = entries
    .map(
      (e) => `
      <tr>
        <td title="${e.created_at}">${e.created_at.split(" ").slice(0, 2).join(" ") || e.created_at}</td>
        <td class="model-badge" title="${e.model}">${e.model}</td>
        <td class="num">${fmtCount(e.input_tokens + e.output_tokens)}</td>
        <td class="num">$${fmtMoney(e.actual_cost_usd || e.estimated_cost_usd)}</td>
        <td>${statusChip(e.status)}</td>
      </tr>`
    )
    .join("");
}

async function refresh() {
  try {
    const [summary, entries] = await Promise.all([
      jsonFetch("/api/summary"),
      jsonFetch("/api/entries"),
    ]);
    const t = summary.totals || {};
    els.spentToday.textContent = `$${fmtMoney(t.estimated_cost_usd)}`;
    els.totalRequests.textContent = fmtCount(t.requests);
    els.totalCost.textContent = `$${fmtMoney(t.estimated_cost_usd)}`;
    renderBudgets(summary.by_key || []);
    renderModels(summary.by_model || []);
    renderLedger(entries.entries || []);
    els.footerUrl.textContent = `${PROXY.replace("http://", "")}`;
    setConn(true, "Connected");
  } catch (err) {
    setConn(false, "Offline: " + err.message);
    els.budgets.innerHTML = '<div class="empty">Proxy unavailable — is it running?</div>';
    els.models.innerHTML = '<div class="empty">Proxy unavailable</div>';
    els.ledgerBody.innerHTML = '<tr><td colspan="5" class="empty">Proxy unavailable</td></tr>';
  }
}

function onOptionsClick(e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
}

async function init() {
  try {
    await refresh();
  } catch (err) {
    setConn(false, "Error loading");
  }
  timerId = setInterval(refresh, REFRESH_MS);
  els.optionsLink.addEventListener("click", onOptionsClick);
}

init();

chrome.runtime.onMessage?.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "REFRESH") refresh();
});
