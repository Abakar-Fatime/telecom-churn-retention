/* Telecom Churn & Retention - dashboard (vanilla JS + Chart.js). */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1, sign = false) => (x == null || isNaN(x) ? "–" : (sign && x > 0 ? "+" : "") + (x * 100).toFixed(d) + "%");
const num = (x, d = 0) => (x == null ? "–" : Number(x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));
const usd = (x, d = 0) => (x == null ? "–" : (x < 0 ? "−$" : "$") + num(Math.abs(x), d));
const usdK = (x) => (Math.abs(x) >= 1000 ? (x < 0 ? "−$" : "$") + (+(Math.abs(x) / 1000).toFixed(Math.abs(x) >= 100000 ? 0 : 1)) + "k" : usd(x));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const alpha = (hex, a) => { const c = hex.replace("#", ""); const n = parseInt(c.length === 3 ? c.split("").map((x) => x + x).join("") : c, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };
const OFFER_COLORS = { discount: "#f59e0b", contract: "#38bdf8", support: "#14b8a6", none: "#9aa3b8" };
const OFFER_SHORT = { discount: "20% discount", contract: "1-year contract", support: "Free tech support", none: "No contact" };
const offerBadge = (o) => `<span class="offer-badge offer-${o}">${esc(OFFER_SHORT[o] || o)}</span>`;

const cache = {};
async function load(name) {
  if (cache[name]) return cache[name];
  let res;
  try { res = await fetch("api/" + name); if (!res.ok) throw new Error(); }
  catch { res = await fetch("data/" + name + ".json"); }
  if (!res.ok) throw new Error("Could not load " + name);
  return (cache[name] = await res.json());
}
let byId = null;
async function customers() { const c = await load("customers"); if (!byId) byId = new Map(c.map((x) => [x.id, x])); return c; }

let charts = [];
function chart(canvas, cfg) { const c = new Chart(canvas, cfg); charts.push(c); return c; }
function clearCharts() { charts.forEach((c) => c.destroy()); charts = []; }
function themeCharts() {
  Chart.defaults.color = css("--muted"); Chart.defaults.borderColor = css("--border"); Chart.defaults.font.family = css("--font");
  Chart.defaults.font.size = 12; Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.boxWidth = 10; Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Object.assign(Chart.defaults.plugins.tooltip, { backgroundColor: css("--surface-3"), titleColor: css("--text"), bodyColor: css("--text"), borderColor: css("--border"), borderWidth: 1, padding: 10 });
}
Chart.register({
  id: "vline",
  afterDraw(c, _a, o) {
    if (!o || o.x == null) return;
    const { ctx, chartArea: { top, bottom }, scales: { x } } = c; const px = x.getPixelForValue(o.x);
    ctx.save(); ctx.strokeStyle = o.color; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
    if (o.label) { ctx.setLineDash([]); ctx.fillStyle = o.color; ctx.font = "600 11px " + css("--font"); ctx.fillText(o.label, px + 6, top + 12); }
    ctx.restore();
  },
});

function setCrumbs(...p) { $("#crumbs").innerHTML = p.map((x, i) => (i === p.length - 1 ? `<b>${esc(x)}</b>` : esc(x))).join(" / "); }
function riskColor(r) { return r >= 0.6 ? css("--bad") : r >= 0.35 ? css("--warn") : css("--good"); }
function riskBar(r) { return `<div class="risk"><div class="bar-inline"><i style="width:${Math.round(r * 100)}%;background:${riskColor(r)}"></i></div><span class="mono">${pct(r, 0)}</span></div>`; }

// ---------------------------------------------------------------- routing
const routes = [
  [/^\/?$/, "overview", renderOverview], [/^\/customers$/, "customers", renderCustomers],
  [/^\/customer\/([\w-]+)$/, "customers", renderCustomer], [/^\/campaign$/, "campaign", renderCampaign],
  [/^\/messages$/, "messages", renderMessages], [/^\/model$/, "model", renderModel],
];
async function router() {
  const path = (location.hash || "#/").slice(1).split("?")[0];
  clearCharts(); themeCharts();
  for (const [re, name, fn] of routes) {
    const m = path.match(re);
    if (m) {
      document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
      try { await fn($("#view"), ...m.slice(1)); } catch (e) { console.error(e); $("#view").innerHTML = `<div class="card empty">Could not load this page: ${esc(e.message)}</div>`; }
      window.scrollTo(0, 0); return;
    }
  }
  location.hash = "#/";
}

// ---------------------------------------------------------------- overview
async function renderOverview(view) {
  setCrumbs("Retention", "Overview");
  const [o, r] = await Promise.all([load("overview"), load("retention")]);
  const best = o.model.comparison[o.model.best_model].test;
  const ours = r.strategies.uplift_value, blanket = r.strategies.highest_risk_discount;
  view.innerHTML = `
  <div class="page-head"><div><h1>Who is leaving, when, and how to keep them</h1>
    <p class="lead">${num(o.customers)} real telecom customers (IBM Telco dataset). The models predict churn risk, estimate how long each active customer will stay, and choose the most profitable retention offer for each one, with an AI-written message ready to send.</p></div>
    <a class="btn primary" href="#/campaign">Plan a campaign</a></div>
  <div class="alert" style="border-color:color-mix(in srgb,var(--accent) 40%,var(--border));background:color-mix(in srgb,var(--accent) 8%,var(--surface))">
    <span class="pulse" style="background:var(--accent);animation:none"></span>
    <div><b>Recommended campaign:</b> with a ${usdK(r.budget)} budget, contact <b>${num(ours.contacted)}</b> customers with tailored offers: expected net gain <b class="pos">${usdK(ours.net_value)}</b>,
    vs ${usdK(blanket.net_value)} for the usual "discount to the riskiest customers" approach (${(ours.net_value / blanket.net_value).toFixed(1)}× better).</div>
    <a class="btn" style="white-space:nowrap" href="#/campaign">See plan →</a></div>
  <div class="grid g-4 section">
    <div class="card kpi"><div class="label">Churn rate</div><div class="value neg">${pct(o.churn_rate)}</div><div class="foot">${num(o.churned)} of ${num(o.customers)} customers left</div></div>
    <div class="card kpi"><div class="label">Active customers</div><div class="value">${num(o.active)}</div><div class="foot">${usd(o.monthly_revenue_active)} monthly revenue</div></div>
    <div class="card kpi"><div class="label">Revenue at risk, next 24 months</div><div class="value warn">${usdK(o.revenue_at_risk_24m)}</div><div class="foot">from expected early departures (survival model)</div></div>
    <div class="card kpi"><div class="label">Churn model accuracy</div><div class="value">${best.roc_auc.toFixed(3)}</div><div class="foot">ROC-AUC on held-out customers · top 10% riskiest: ${pct(best.churn_rate_top10, 0)} really churn</div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>Why customers leave</h2><div class="card-sub">Strongest churn drivers (mean |SHAP| from the gradient-boosting model)</div></div></div><div class="chart-box"><canvas id="drivers"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>How long customers stay</h2><div class="card-sub">Share still active after N months, by contract (Kaplan-Meier)</div></div></div><div class="chart-box"><canvas id="km"></canvas></div></div>
  </div>
  <div class="grid g-3 section">
    <div class="card"><div class="card-head"><h2>Churn by contract</h2></div><div class="chart-box short"><canvas id="byContract"></canvas></div></div>
    <div class="card"><div class="card-head"><h2>Churn by tenure (months)</h2></div><div class="chart-box short"><canvas id="byTenure"></canvas></div></div>
    <div class="card"><div class="card-head"><h2>Churn by payment method</h2></div><div class="chart-box short"><canvas id="byPay"></canvas></div></div>
  </div>`;
  const gi = o.model.global_importance.slice(0, 9);
  chart($("#drivers"), { type: "bar", data: { labels: gi.map((g) => g.feature), datasets: [{ data: gi.map((g) => g.mean_abs_shap), backgroundColor: alpha(css("--bad"), 0.7), borderRadius: 4 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "impact on churn (log-odds)" } }, y: { grid: { display: false } } } } });
  const km = o.survival.km_by_contract, cc = { "Month-to-month": css("--bad"), "One year": css("--warn"), "Two year": css("--good") };
  chart($("#km"), { type: "line", data: { labels: km.months, datasets: Object.entries(km.curves).map(([k, v]) => ({ label: k, data: v.map((x) => x * 100), borderColor: cc[k], pointRadius: 0, borderWidth: 2.4, stepped: true })) },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } }, x: { title: { display: true, text: "months as a customer" }, grid: { display: false } } } } });
  const bar = (id, rows, labelFn) => chart($(id), { type: "bar", data: { labels: rows.map(labelFn), datasets: [{ data: rows.map((r) => r.churn_rate * 100), backgroundColor: rows.map((r) => alpha(riskColor(r.churn_rate * 1.6), 0.75)), borderRadius: 5 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (t) => `${t.parsed.y.toFixed(1)}% churn · ${num(rows[t.dataIndex].customers)} customers` } } }, scales: { y: { ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false } } } } });
  bar("#byContract", o.churn_by.contract, (r) => r.group);
  bar("#byTenure", o.churn_by.tenure, (r) => r.group);
  bar("#byPay", o.churn_by.payment, (r) => r.group.replace(" (automatic)", " (auto)").replace("Electronic check", "E-check"));
}

// ---------------------------------------------------------------- customers list
const listState = { contract: "", internet: "", offer: "", sort: "revenue_at_risk", page: 0 };
async function renderCustomers(view) {
  setCrumbs("Retention", "At-risk customers");
  const all = await customers();
  view.innerHTML = `
  <div class="page-head"><div><h1>At-risk customers</h1><p class="lead">All ${num(all.length)} active customers, scored for churn risk, expected time remaining and value. Click a customer for the full profile, reasons and the recommended offer.</p></div></div>
  <div class="card">
    <div class="filters">
      <select id="f-contract"><option value="">All contracts</option><option>Month-to-month</option><option>One year</option><option>Two year</option></select>
      <select id="f-internet"><option value="">All internet types</option><option>Fiber optic</option><option>DSL</option><option>No</option></select>
      <select id="f-offer"><option value="">Any recommendation</option><option value="targeted">Recommended for contact</option><option value="discount">20% discount</option><option value="contract">1-year contract</option><option value="support">Free tech support</option><option value="none">No contact</option></select>
      <select id="f-sort"><option value="revenue_at_risk">Sort: revenue at risk</option><option value="risk">Sort: churn risk</option><option value="p6">Sort: 6-month churn chance</option><option value="best_net">Sort: value of acting</option></select>
      <span class="muted" id="f-count" style="margin-left:auto"></span>
    </div>
    <div style="overflow-x:auto"><table class="table"><thead><tr><th>Customer</th><th>Contract</th><th class="num">Tenure</th><th class="num">Monthly bill</th><th>Churn risk</th><th class="num">Leave in 6 mo.</th><th class="num">Revenue at risk</th><th>Recommendation</th></tr></thead><tbody id="rows"></tbody></table></div>
    <div class="pager"><button class="btn" id="prev">← Prev</button><span id="pageinfo"></span><button class="btn" id="next">Next →</button></div>
  </div>`;
  ["contract", "internet", "offer", "sort"].forEach((k) => { const el = $("#f-" + k); el.value = listState[k]; el.onchange = () => { listState[k] = el.value; listState.page = 0; draw(); }; });
  $("#prev").onclick = () => { listState.page = Math.max(0, listState.page - 1); draw(); };
  $("#next").onclick = () => { listState.page += 1; draw(); };
  function draw() {
    let rows = all.filter((c) => (!listState.contract || c.contract === listState.contract) && (!listState.internet || c.internet === listState.internet)
      && (!listState.offer || (listState.offer === "targeted" ? c.recommended !== "none" : c.recommended === listState.offer)));
    const key = listState.sort;
    rows = rows.map((c) => ({ ...c, best_net: c.recommended !== "none" ? c.net[c.recommended] : -1e9 })).sort((a, b) => b[key] - a[key]);
    const pages = Math.max(1, Math.ceil(rows.length / 25)); listState.page = Math.min(listState.page, pages - 1);
    $("#f-count").textContent = `${num(rows.length)} customers`;
    $("#pageinfo").textContent = `Page ${listState.page + 1} of ${pages}`;
    $("#rows").innerHTML = rows.slice(listState.page * 25, listState.page * 25 + 25).map((c) => `
      <tr class="click" data-id="${esc(c.id)}"><td><b class="mono">${esc(c.id)}</b><div class="role">${esc(c.internet === "No" ? "phone only" : c.internet)} · ${c.services} services</div></td>
      <td>${esc(c.contract)}</td><td class="num">${c.tenure} mo</td><td class="num">${usd(c.monthly, 2)}</td><td>${riskBar(c.risk)}</td>
      <td class="num">${pct(c.p6, 1)}</td><td class="num">${usd(c.revenue_at_risk)}</td><td>${offerBadge(c.recommended)}</td></tr>`).join("");
    document.querySelectorAll("tr.click").forEach((tr) => (tr.onclick = () => (location.hash = "#/customer/" + tr.dataset.id)));
  }
  draw();
}

// ---------------------------------------------------------------- customer profile
let showTruth = false, msgLang = "en";
function gauge(r) {
  const a = Math.PI * r, x = 75 - 60 * Math.cos(a), y = 78 - 60 * Math.sin(a);
  return `<div class="gauge"><svg viewBox="0 0 150 84"><path d="M15 78 A60 60 0 0 1 135 78" fill="none" stroke="${css("--surface-3")}" stroke-width="12" stroke-linecap="round"/>
    <path d="M15 78 A60 60 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}" fill="none" stroke="${riskColor(r)}" stroke-width="12" stroke-linecap="round"/></svg><div class="g-val" style="color:${riskColor(r)}">${pct(r, 0)}</div></div>`;
}
async function renderCustomer(view, id) {
  await customers();
  const c = byId.get(id);
  if (!c) throw new Error(`Customer ${id} is not an active customer`);
  const o = await load("overview");
  setCrumbs("Retention", "Customers", id);
  const offers = ["discount", "contract", "support"];
  view.innerHTML = `
  <div class="card profile-head">
    <div style="text-align:center">${gauge(c.risk)}<div class="muted" style="font-size:12px">churn risk score</div></div>
    <div><div class="muted" style="font-size:12px">Customer</div><h1 class="mono" style="font-size:22px">${esc(c.id)}</h1>
      <div class="facts-grid" style="margin-top:10px">
        <div><div class="k">Contract</div><div class="v">${esc(c.contract)}</div></div><div><div class="k">Tenure</div><div class="v">${c.tenure} months</div></div>
        <div><div class="k">Monthly bill</div><div class="v">${usd(c.monthly, 2)}</div></div><div><div class="k">Internet</div><div class="v">${esc(c.internet)}</div></div>
        <div><div class="k">Tech support</div><div class="v">${esc(c.tech_support)}</div></div><div><div class="k">Payment</div><div class="v">${esc(c.payment)}</div></div>
        <div><div class="k">Services</div><div class="v">${c.services}</div></div><div><div class="k">Senior citizen</div><div class="v">${c.senior ? "Yes" : "No"}</div></div>
      </div></div>
    <div style="text-align:right"><div class="muted" style="font-size:12px">Recommendation</div><div style="margin:6px 0 10px">${offerBadge(c.recommended)}</div>
      <label class="toggle" title="Show the true offer effects known from the simulation"><input type="checkbox" id="truth" ${showTruth ? "checked" : ""}><span class="sw"></span>Simulation truth</label></div>
  </div>
  <div class="grid g-4 section">
    <div class="card kpi"><div class="label">Chance of leaving in 6 months</div><div class="value ${c.p6 > 0.15 ? "neg" : ""}">${pct(c.p6, 1)}</div><div class="foot">survival model</div></div>
    <div class="card kpi"><div class="label">Expected months, next 24</div><div class="value">${c.expected_months.toFixed(1)}</div><div class="foot">of 24 possible</div></div>
    <div class="card kpi"><div class="label">Revenue at risk</div><div class="value warn">${usd(c.revenue_at_risk)}</div><div class="foot">expected loss over 24 months</div></div>
    <div class="card kpi"><div class="label">Value if retained</div><div class="value">${usd(c.value_if_retained)}</div><div class="foot">revenue over 24 months if they stay</div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>Why this customer may leave</h2><div class="card-sub">Top factors pushing the risk up (SHAP)</div></div></div>
      ${c.drivers.length ? c.drivers.map((d, i) => `<div class="reason"><span class="num">${i + 1}</span><span>${esc(d.feature)}</span><span class="muted mono" style="margin-left:auto">+${d.impact.toFixed(2)}</span></div>`).join("") : `<div class="muted">No strong risk factors: this customer looks stable.</div>`}
      <div class="chart-box short" style="margin-top:14px"><canvas id="surv"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Which offer works best?</h2><div class="card-sub">Estimated churn reduction per offer (uplift model) and expected net value after costs</div></div></div>
      <div class="chart-box short"><canvas id="offers"></canvas></div>
      <table class="table" style="margin-top:8px"><thead><tr><th>Offer</th><th class="num">Churn reduction</th>${showTruth ? '<th class="num">True</th>' : ""}<th class="num">Cost</th><th class="num">Net value</th></tr></thead><tbody>
      ${offers.map((k) => `<tr ${k === c.recommended ? 'style="background:color-mix(in srgb,var(--accent) 10%,transparent)"' : ""}><td>${offerBadge(k)}</td><td class="num">${pct(c.uplift[k], 1, true)}</td>${showTruth ? `<td class="num warn">${pct(c.uplift_true[k], 1, true)}</td>` : ""}<td class="num">${usd(c.spend[k])}</td><td class="num ${c.net[k] > 0 ? "pos" : "neg"}" style="font-weight:700">${usd(c.net[k])}</td></tr>`).join("")}</tbody></table>
      <div class="foot-note">${c.recommended === "none" ? "No offer has a positive expected net value for this customer (or the campaign budget went to better targets), so the best action is not to contact them." : `Recommended: ${esc(o.offers[c.recommended].label)}.`}</div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Retention message</h2><div class="card-sub">Written from this customer's facts only; every message passes guardrail checks before it can be sent</div></div>
    <div style="display:flex;gap:10px;align-items:center"><select id="msg-offer" style="width:auto">${offers.map((k) => `<option value="${k}" ${k === (c.recommended === "none" ? "support" : c.recommended) ? "selected" : ""}>${OFFER_SHORT[k]}</option>`).join("")}</select>
      <div class="tabs"><button data-l="en" class="${msgLang === "en" ? "on" : ""}">English</button><button data-l="fr" class="${msgLang === "fr" ? "on" : ""}">Français</button></div>
      <button class="btn primary" id="gen">Generate with AI</button></div></div>
    <div class="sms" id="sms"></div><div class="checks" id="checks"></div></div>`;
  $("#truth").onchange = (e) => { showTruth = e.target.checked; router(); };
  chart($("#surv"), { type: "line", data: { labels: c.survival.map((_, i) => i + 1), datasets: [{ label: "Chance still a customer", data: c.survival.map((s) => s * 100), borderColor: css("--accent-2"), backgroundColor: alpha(css("--accent"), 0.12), fill: true, pointRadius: 0, borderWidth: 2.2, tension: 0.3 }] },
    options: { plugins: { legend: { display: false }, title: { display: true, text: "Chance this customer is still with us, next 24 months", color: css("--muted"), font: { weight: 500 } }, vline: { x: 5, color: css("--warn"), label: "6 months" } },
      scales: { y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false }, title: { display: true, text: "months from now" } } } } });
  chart($("#offers"), { type: "bar", data: { labels: offers.map((k) => OFFER_SHORT[k]), datasets: [
    { label: "Estimated", data: offers.map((k) => c.uplift[k] * 100), backgroundColor: offers.map((k) => alpha(OFFER_COLORS[k], 0.8)), borderRadius: 5 },
    ...(showTruth ? [{ label: "True (simulation)", data: offers.map((k) => c.uplift_true[k] * 100), backgroundColor: alpha(css("--warn"), 0.35), borderColor: css("--warn"), borderWidth: 1.5, borderRadius: 5 }] : [])] },
    options: { plugins: { legend: { display: showTruth, position: "bottom" } }, scales: { y: { title: { display: true, text: "churn reduction (points)" }, ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false } } } } });

  const showMsg = (res) => {
    $("#sms").textContent = res.text;
    $("#checks").innerHTML = `<span class="badge good">✓ Guardrails passed</span><span class="badge accent">${esc(res.source)}</span>` +
      (res.problems ? `<span class="badge invalid">AI draft rejected: ${esc(res.problems.join(", "))}</span>` : "");
  };
  const local = () => {
    const off = $("#msg-offer").value;
    if (off === c.recommended && c.message[msgLang]) return showMsg({ text: c.message[msgLang], source: "template" });
    return gen(false);
  };
  async function gen(useLlm) {
    $("#sms").innerHTML = `<span class="typing"><span></span><span></span><span></span></span>`;
    try {
      const r = await fetch("api/message", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer_id: c.id, offer: $("#msg-offer").value, lang: msgLang, use_llm: useLlm }) });
      if (!r.ok) throw new Error();
      showMsg(await r.json());
    } catch { $("#sms").textContent = c.message[msgLang] || "Start the backend (uvicorn churnlab.api:app) to generate messages for other offers."; $("#checks").innerHTML = ""; }
  }
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => { msgLang = b.dataset.l; document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b)); local(); }));
  $("#msg-offer").onchange = local;
  $("#gen").onclick = () => gen(true);
  local();
}

// ---------------------------------------------------------------- campaign
async function renderCampaign(view) {
  setCrumbs("Retention", "Campaign planner");
  const [all, r] = await Promise.all([customers(), load("retention")]);
  const S = r.strategies;
  const names = { random: "Random customers, random offer", highest_risk_discount: "Riskiest customers, 20% discount", uplift_value: "Uplift + value (this project)", oracle: "Oracle (knows true effects)" };
  const colors = { random: css("--neutral"), highest_risk_discount: css("--warn"), uplift_value: css("--accent-2"), oracle: css("--info") };
  view.innerHTML = `
  <div class="page-head"><div><h1>Campaign planner</h1><p class="lead">Each customer gets the offer with the highest expected net value (churn reduction × value if retained − offer cost − $5 contact cost), and customers are taken in order of that value until the budget is spent. Customers for whom no offer pays off are left alone.</p></div></div>
  <div class="grid g-12">
    <div class="card"><div class="field"><label>Campaign budget <b id="b-v"></b></label><input type="range" id="budget" min="5000" max="120000" step="5000" value="${r.budget}"></div>
      <div class="stat-list" id="plan"></div><div class="foot-note">The model picks customers whose estimates look best, so its estimate is optimistic (the "winner's curse"). In the simulation the realised value was ${pct(r.estimate_realisation_ratio, 0)} of the estimate, so the realistic figure applies that adjustment.</div></div>
    <div class="card"><div class="card-head"><div><h2>Who gets which offer</h2><div class="card-sub">Number of customers contacted per offer at this budget</div></div></div><div class="chart-box short"><canvas id="mix"></canvas></div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Net value by targeting strategy</h2><div class="card-sub">Scored against the true offer effects from the simulation, at each budget</div></div></div><div class="chart-box tall"><canvas id="curve"></canvas></div></div>
  <div class="card section"><div class="card-head"><div><h2>Strategy comparison at ${usdK(r.budget)}</h2><div class="card-sub">Ground truth from the simulation; held-out check = what the company could measure on its last randomised test</div></div></div>
    <div style="overflow-x:auto"><table class="table"><thead><tr><th>Strategy</th><th class="num">Contacted</th><th class="num">Churners prevented</th><th class="num">Revenue saved</th><th class="num">Cost</th><th class="num">Net value</th><th class="num">ROI</th></tr></thead><tbody>
    ${Object.entries(S).map(([k, s]) => `<tr><td><span class="dot" style="background:${colors[k]};margin-right:8px"></span><b>${names[k]}</b></td><td class="num">${num(s.contacted)}</td><td class="num">${s.churners_prevented.toFixed(1)}</td><td class="num">${usd(s.revenue_saved)}</td><td class="num">${usd(s.cost)}</td><td class="num ${s.net_value > 0 ? "pos" : "neg"}" style="font-weight:700">${usd(s.net_value)}</td><td class="num">${pct(s.roi, 0)}</td></tr>`).join("")}</tbody></table></div>
    <div class="foot-note">${(() => { const h = S.uplift_value.holdout_check; return `Held-out check, which a real company could run on its last randomised wave: among the customers this policy picks, churn was ${pct(h.churn_control)} in the control group vs ${pct(h.churn_with_offer)} with the recommended offer (${h.n_control} vs ${h.n_offer} customers), a reduction of ${(h.reduction * 100).toFixed(1)} points (95% CI ${(h.ci_low * 100).toFixed(1)} to ${(h.ci_high * 100).toFixed(1)}). ${h.ci_low > 0 ? "The improvement is statistically significant." : "The interval includes zero, so a larger test is needed to confirm it."}`; })()}</div></div>`;
  const ranked = all.map((c) => { const k = ["discount", "contract", "support"].reduce((a, b) => (c.net[b] > c.net[a] ? b : a)); return { k, net: c.net[k], spend: c.spend[k] }; })
    .filter((x) => x.net > 0).sort((a, b) => b.net - a.net);
  let mixChart = null;
  const update = () => {
    const B = +$("#budget").value; $("#b-v").textContent = usd(B);
    let spent = 0, net = 0; const mix = { discount: 0, contract: 0, support: 0 };
    for (const x of ranked) { if (spent + x.spend > B) continue; spent += x.spend; net += x.net; mix[x.k]++; }
    const n = mix.discount + mix.contract + mix.support;
    const ratio = r.estimate_realisation_ratio || 1;
    $("#plan").innerHTML = [["Customers contacted", num(n)], ["Budget used", usd(spent)], ["Model estimate of net value", usd(net)],
      ["Realistic expectation", `<span class="pos">${usd(net * ratio)}</span>`],
      ["Customers worth contacting at any budget", num(ranked.length)]].map(([k, v]) => `<div class="stat-row"><span class="k">${k}</span><span class="v">${v}</span></div>`).join("");
    if (mixChart) { mixChart.destroy(); charts = charts.filter((x) => x !== mixChart); }
    mixChart = chart($("#mix"), { type: "bar", data: { labels: ["20% discount", "1-year contract", "Free tech support"], datasets: [{ data: [mix.discount, mix.contract, mix.support], backgroundColor: [OFFER_COLORS.discount, OFFER_COLORS.contract, OFFER_COLORS.support].map((c) => alpha(c, 0.8)), borderRadius: 6, barPercentage: 0.55 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } } });
  };
  $("#budget").oninput = update; update();
  const cv = r.budget_curve;
  chart($("#curve"), { type: "line", data: { labels: cv.map((x) => usdK(x.budget)), datasets: Object.keys(names).map((k) => ({ label: names[k], data: cv.map((x) => x[k]), borderColor: colors[k], backgroundColor: colors[k], borderWidth: k === "uplift_value" ? 3 : 2, borderDash: k === "oracle" ? [6, 4] : [], pointRadius: 3, tension: 0.25 })) },
    options: { plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (t) => `${t.dataset.label}: ${usd(t.parsed.y)}` } } }, scales: { y: { ticks: { callback: (v) => usdK(v) }, title: { display: true, text: "net value (revenue saved − cost)" } }, x: { title: { display: true, text: "campaign budget" }, grid: { display: false } } } } });
}

// ---------------------------------------------------------------- messages
async function renderMessages(view) {
  setCrumbs("Retention", "AI messages");
  const [ev, all] = await Promise.all([load("messages_eval"), customers()]);
  const sample = all.find((c) => c.recommended === "discount") || all[0];
  const labels = { invented_discount: "Invented discount", wrong_price: "Wrong price", forbidden_promise: "Forbidden promise", wrong_language: "Wrong language", too_long: "Too long", offer_missing: "Offer missing" };
  view.innerHTML = `
  <div class="page-head"><div><h1>AI-written retention messages</h1><p class="lead">An LLM (local via Ollama, or any OpenAI-compatible API) writes each message in English or French from the customer's facts and the chosen offer. Guardrails then check every draft; if a draft fails, a safe template is sent instead, so a wrong price or invented promise never reaches a customer.</p></div></div>
  <div class="grid g-3">
    <div class="card kpi"><div class="label">Messages tested</div><div class="value">${num(ev.messages)}</div><div class="foot">${ev.customers} customers × 3 offers × 2 languages</div></div>
    <div class="card kpi"><div class="label">Clean messages passed</div><div class="value pos">${pct(ev.clean_pass_rate, 0)}</div><div class="foot">no false alarms on correct messages</div></div>
    <div class="card kpi"><div class="label">Injected errors caught</div><div class="value pos">${pct(ev.caught_rate, 1)}</div><div class="foot">${num(ev.injected_errors)} deliberately broken messages</div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>Guardrail catch rate by error type</h2><div class="card-sub">Typical LLM mistakes, injected on purpose</div></div></div><div class="chart-box"><canvas id="ev"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Try the guardrails</h2><div class="card-sub">Customer <span class="mono">${esc(sample.id)}</span>, offer: 20% discount. Edit the message and check it.</div></div></div>
      <div class="tabs" style="margin-bottom:10px"><button data-l="en" class="on">English</button><button data-l="fr">Français</button></div>
      <textarea id="try"></textarea><div style="display:flex;gap:10px;margin-top:10px"><button class="btn primary" id="check">Check message</button><button class="btn" id="break">Break it (add a fake offer)</button></div>
      <div class="checks" id="try-res"></div></div>
  </div>`;
  chart($("#ev"), { type: "bar", data: { labels: Object.keys(ev.by_type).map((k) => labels[k] || k), datasets: [{ data: Object.values(ev.by_type).map((v) => v * 100), backgroundColor: alpha(css("--good"), 0.75), borderRadius: 5 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } }, y: { grid: { display: false } } } } });
  let lang = "en";
  const fill = async () => {
    try { const r = await fetch("api/message", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer_id: sample.id, offer: "discount", lang, use_llm: false }) });
      $("#try").value = (await r.json()).text; } catch { $("#try").value = sample.message[lang] || ""; }
    $("#try-res").innerHTML = "";
  };
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => { lang = b.dataset.l; document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b)); fill(); }));
  $("#break").onclick = () => { $("#try").value += lang === "en" ? " Plus 50% off your next phone, guaranteed forever!" : " En plus, 50 % sur votre prochain téléphone, garanti pour toujours !"; };
  $("#check").onclick = async () => {
    try { const r = await fetch("api/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer_id: sample.id, offer: "discount", lang, text: $("#try").value }) });
      const j = await r.json();
      $("#try-res").innerHTML = j.ok ? `<span class="badge good">✓ Safe to send</span>` : j.problems.map((p) => `<span class="badge bad">✗ ${esc(p)}</span>`).join("");
    } catch { $("#try-res").innerHTML = `<span class="badge invalid">Start the backend to run the checks</span>`; }
  };
  fill();
}

// ---------------------------------------------------------------- model
async function renderModel(view) {
  setCrumbs("Retention", "Models & validation");
  const [o, r] = await Promise.all([load("overview"), load("retention")]);
  const M = o.model, cmp = M.comparison;
  const rows = [["CV ROC-AUC (5-fold, train)", (k) => cmp[k].cv_roc_auc.toFixed(3)], ["Test ROC-AUC", (k) => cmp[k].test.roc_auc.toFixed(3)], ["Test PR-AUC", (k) => cmp[k].test.pr_auc.toFixed(3)],
    ["Brier score (lower is better)", (k) => cmp[k].test.brier.toFixed(3)], ["Churn rate in top 10% riskiest", (k) => pct(cmp[k].test.churn_rate_top10, 1)], ["Lift in top 10%", (k) => cmp[k].test.lift_top10.toFixed(2) + "×"],
    ["Churners caught in top 20%", (k) => pct(cmp[k].test.capture_top20, 1)]];
  view.innerHTML = `
  <div class="page-head"><div><h1>Models &amp; validation</h1><p class="lead">How each model was checked: churn classifiers on held-out customers, survival models by concordance, and uplift models against the simulation's true offer effects.</p></div></div>
  <div class="grid g-21">
    <div class="card"><div class="card-head"><div><h2>Churn classifier: simple vs complex</h2><div class="card-sub">Chosen by cross-validated AUC: <b>${M.best_model === "logistic" ? "logistic regression" : "LightGBM"}</b>. On this tidy tabular data the simple model is as good as gradient boosting, and easier to explain.</div></div></div>
      <table class="table"><thead><tr><th>Metric</th><th class="num">Logistic regression</th><th class="num">LightGBM</th></tr></thead><tbody>
      ${rows.map(([l, f]) => `<tr><td>${l}</td><td class="num">${f("logistic")}</td><td class="num">${f("lightgbm")}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><div class="card-head"><div><h2>Survival models</h2><div class="card-sub">Concordance on held-out customers (1.0 = perfect ordering of who leaves first)</div></div></div>
      <div class="stat-list">${Object.entries(o.survival.concordance).map(([k, v]) => `<div class="stat-row"><span class="k">${k === "cox" ? "Cox proportional hazards" : "Weibull AFT (used for value)"}</span><span class="v">${v.toFixed(3)}</span></div>`).join("")}</div>
      <div class="chart-box short" style="margin-top:10px"><canvas id="tr"></canvas></div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>Lift by risk decile</h2><div class="card-sub">Actual churn rate in each tenth of held-out customers, ranked by predicted risk</div></div></div><div class="chart-box"><canvas id="dec"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Calibration</h2><div class="card-sub">Predicted vs observed churn rate (diagonal = perfectly calibrated)</div></div></div><div class="chart-box"><canvas id="cal"></canvas></div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Uplift models vs truth</h2><div class="card-sub">Correlation between estimated and true churn reduction per customer, from ${num(r.campaign_summary.observations)} simulated campaign observations (${r.campaign_summary.waves} randomised waves)</div></div></div>
    <div class="grid g-3">${Object.entries(r.uplift_corr_with_truth).map(([k, v]) => `<div class="kpi"><div class="label">${OFFER_SHORT[k]}</div><div class="value">${v.toFixed(2)}</div><div class="foot">churn ${pct(r.campaign_summary.arm_churn_rate[k])} vs ${pct(r.campaign_summary.arm_churn_rate.control)} in control</div></div>`).join("")}</div></div>`;
  const tr = o.survival.time_ratios.slice().sort((a, b) => b.time_ratio - a.time_ratio);
  chart($("#tr"), { type: "bar", data: { labels: tr.map((t) => t.feature.replace(/_/g, " ").replace("PaymentMethod ", "Pays by ").replace("Contract ", "Contract: ").replace("InternetService ", "Internet: ").replace(" Yes", "")), datasets: [{ data: tr.map((t) => t.time_ratio), backgroundColor: tr.map((t) => alpha(t.time_ratio > 1 ? css("--good") : css("--bad"), 0.75)), borderRadius: 4 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, title: { display: true, text: "Time ratio: >1 stays longer, <1 leaves sooner", color: css("--muted"), font: { weight: 500 } } }, scales: { x: { type: "logarithmic" }, y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 10.5 } } } } } });
  chart($("#dec"), { type: "bar", data: { labels: M.decile_churn_rate.map((_, i) => "D" + (i + 1)), datasets: [{ data: M.decile_churn_rate.map((x) => x * 100), backgroundColor: M.decile_churn_rate.map((x) => alpha(riskColor(x * 1.4), 0.75)), borderRadius: 5 }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false }, title: { display: true, text: "risk decile (D1 = highest predicted risk)" } } } } });
  chart($("#cal"), { type: "scatter", data: { datasets: [
    { label: "Model", data: M.calibration.predicted.map((p, i) => ({ x: p * 100, y: M.calibration.observed[i] * 100 })), backgroundColor: css("--accent-2"), pointRadius: 5, showLine: true, borderColor: css("--accent-2") },
    { label: "Perfect", data: [{ x: 0, y: 0 }, { x: 100, y: 100 }], showLine: true, borderColor: css("--faint"), borderDash: [5, 4], pointRadius: 0 }] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { x: { min: 0, max: 100, title: { display: true, text: "predicted churn %" } }, y: { min: 0, max: 100, title: { display: true, text: "observed churn %" } } } } });
}

// ---------------------------------------------------------------- boot
$("#find-form").onsubmit = async (e) => { e.preventDefault(); const v = $("#find-input").value.trim().toUpperCase(); if (!v) return; await customers();
  if (byId.has(v)) { $("#find-input").value = ""; location.hash = "#/customer/" + v; } else { $("#find-input").value = ""; $("#find-input").placeholder = `${v} is not an active customer`; } };
$("#theme-btn").onclick = () => { document.documentElement.classList.toggle("light"); try { localStorage.setItem("tc-theme", document.documentElement.classList.contains("light") ? "light" : "dark"); } catch (e) {} router(); };
window.addEventListener("hashchange", router);
router();
