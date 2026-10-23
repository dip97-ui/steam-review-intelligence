/* SteamLens dashboard logic - light/dark themable */
const THEMES = {
  light: {
    ink: "#28394d", dim: "#66788c", grid: "#e2e8f0",
    accent: "#2b6cb0", accentFill: "rgba(43,108,176,.55)",
    positive: "#5a9e2f", posFill: "rgba(90,158,47,.8)",
    negative: "#c0392b", negFill: "rgba(192,57,43,.75)",
    neutral: "#66788c", cardDeep: "#ffffff",
  },
  dark: {
    ink: "#c7d5e0", dim: "#77858f", grid: "#1e2c3d",
    accent: "#5c94d6", accentFill: "rgba(92,148,214,.5)",
    positive: "#8bc53f", posFill: "rgba(139,197,63,.75)",
    negative: "#d9534f", negFill: "rgba(217,83,79,.7)",
    neutral: "#77858f", cardDeep: "#1b2838",
  },
};

function currentThemeName() {
  return localStorage.getItem("steamlens-theme") === "dark" ? "dark" : "light";
}
let C = THEMES[currentThemeName()];

Chart.defaults.color = C.ink;
Chart.defaults.borderColor = C.grid;
Chart.defaults.font.size = 12;

const fmt = (n) => n.toLocaleString("en-US");

async function loadSummary() {
  const res = await fetch("/api/summary");
  return res.json();
}

function renderKpis(k) {
  const cards = [
    [fmt(k.total_reviews), "reviews analyzed", ""],
    [k.pct_positive + "%", "recommend their game", "pos"],
    [k.avg_sentiment, "avg text sentiment (-1 to 1)", "accent"],
    [k.sentiment_vote_agreement + "%", "sentiment-vote agreement", "accent"],
    [fmt(k.avg_playtime_hours) + "h", "avg playtime at review", ""],
    [k.games, "games covered", ""],
  ];
  document.getElementById("kpis").innerHTML = cards.map(
    ([num, lbl, cls]) => `<div class="kpi"><div class="num ${cls}">${num}</div><div class="lbl">${lbl}</div></div>`
  ).join("");
}

function renderInsights(insights) {
  document.getElementById("insights").innerHTML =
    insights.map((t) => `<li>${t}</li>`).join("");
}

function renderSentiment(dist) {
  new Chart(document.getElementById("sentimentChart"), {
    type: "doughnut",
    data: {
      labels: ["Positive", "Neutral", "Negative"],
      datasets: [{
        data: [dist.positive, dist.neutral, dist.negative],
        backgroundColor: [C.positive, C.neutral, C.negative],
        borderColor: C.cardDeep, borderWidth: 3,
      }],
    },
    options: {
      maintainAspectRatio: false, cutout: "58%",
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function renderMonthly(monthly) {
  new Chart(document.getElementById("monthlyChart"), {
    data: {
      labels: monthly.map((m) => m.month),
      datasets: [
        {
          type: "bar", label: "Reviews",
          data: monthly.map((m) => m.reviews),
          backgroundColor: C.accentFill,
          borderColor: C.accent, borderWidth: 1, yAxisID: "y",
        },
        {
          type: "line", label: "Avg sentiment",
          data: monthly.map((m) => m.avg_sentiment),
          borderColor: C.positive, backgroundColor: C.positive,
          tension: .3, pointRadius: 2, yAxisID: "y1",
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: {
        y: { position: "left", title: { display: true, text: "reviews" } },
        y1: { position: "right", grid: { drawOnChartArea: false },
              title: { display: true, text: "sentiment" } },
        x: { ticks: { maxTicksLimit: 12 } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function renderTerms(id, terms, color) {
  new Chart(document.getElementById(id), {
    type: "bar",
    data: {
      labels: terms.map((t) => t[0]),
      datasets: [{ data: terms.map((t) => t[1]), backgroundColor: color }],
    },
    options: {
      indexAxis: "y", maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: "mentions" } } },
    },
  });
}

function renderThemes(themes) {
  new Chart(document.getElementById("themeChart"), {
    type: "bar",
    data: {
      labels: themes.map((t) => t.theme),
      datasets: [
        { label: "% of reviews mentioning theme",
          data: themes.map((t) => t.share),
          backgroundColor: C.accentFill },
        { label: "% positive within theme",
          data: themes.map((t) => t.pct_positive),
          backgroundColor: C.posFill },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: { y: { max: 100, title: { display: true, text: "%" } } },
    },
  });
}

function renderPlaytime(rows) {
  new Chart(document.getElementById("playtimeChart"), {
    type: "bar",
    data: {
      labels: rows.map((r) => r.bucket),
      datasets: [{ label: "% positive",
        data: rows.map((r) => r.pct_positive),
        backgroundColor: rows.map((r) =>
          r.pct_positive >= 75 ? C.posFill : C.negFill) }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (c) =>
          `${c.parsed.y}% positive (${fmt(rows[c.dataIndex].reviews)} reviews)` } } },
      scales: { y: { max: 100, title: { display: true, text: "% positive" } } },
    },
  });
}

function renderLength(rows) {
  new Chart(document.getElementById("lengthChart"), {
    type: "bar",
    data: {
      labels: rows.map((r) => r.bucket),
      datasets: [{ data: rows.map((r) => r.reviews),
        backgroundColor: C.accentFill }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { title: { display: true, text: "reviews" } } },
    },
  });
}

const CHART_IDS = ["sentimentChart", "monthlyChart", "posTermsChart",
  "negTermsChart", "themeChart", "playtimeChart", "lengthChart"];

function renderCharts(data) {
  for (const id of CHART_IDS) {
    const existing = Chart.getChart(id);
    if (existing) existing.destroy();
  }
  renderSentiment(data.sentiment_distribution);
  renderMonthly(data.monthly);
  renderTerms("posTermsChart", data.top_positive_terms.slice(0, 10), C.posFill);
  renderTerms("negTermsChart", data.top_negative_terms.slice(0, 10), C.negFill);
  renderThemes(data.themes);
  renderPlaytime(data.playtime_buckets);
  renderLength(data.length_buckets);
}

let chartData = null;

function applyTheme(name) {
  C = THEMES[name];
  document.documentElement.dataset.theme = name;
  localStorage.setItem("steamlens-theme", name);
  Chart.defaults.color = C.ink;
  Chart.defaults.borderColor = C.grid;
  const btn = document.getElementById("theme-toggle");
  btn.textContent = "THEME: " + name.toUpperCase();
  btn.setAttribute("aria-pressed", name === "dark" ? "true" : "false");
  if (chartData) renderCharts(chartData);
}

document.getElementById("theme-toggle").addEventListener("click", () => {
  applyTheme(currentThemeName() === "dark" ? "light" : "dark");
});
applyTheme(currentThemeName());

function renderGames(games) {
  const tbody = document.querySelector("#gamesTable tbody");
  tbody.innerHTML = games.map((g) => `
    <tr>
      <td class="game-name">${g.game}</td>
      <td>${fmt(g.reviews)}</td>
      <td><div class="posbar"><span style="width:${g.pct_positive}%"></span></div>
          <span class="posnum">${g.pct_positive}%</span></td>
      <td>${g.avg_sentiment}</td>
      <td>${fmt(g.avg_playtime_hours)}h</td>
      <td>${g.most_praised_theme || "-"}</td>
      <td>${g.most_complained_theme || "-"}</td>
    </tr>`).join("");
}

function renderFunnel(report) {
  const max = Math.max(...report.steps.map((s) => s.remaining), 1);
  document.getElementById("funnel").innerHTML = report.steps.map((s) => `
    <div class="funnel-step">
      <div class="step-name">${s.step}</div>
      <div class="bar" style="width:${Math.max(4, 260 * s.remaining / max)}px"></div>
      <div class="counts">${s.removed > 0 ? `-${fmt(s.removed)} · ` : ""}<b>${fmt(s.remaining)}</b> rows</div>
    </div>`).join("") + `
    <div class="funnel-step" style="border:1px solid var(--accent)">
      <div class="step-name"><b>Kept for analysis</b></div>
      <div class="counts"><b>${report.pct_kept}%</b> of raw rows</div>
    </div>`;
}

/* ---------------- review explorer ---------------- */
const state = { page: 1 };

function explorerParams() {
  const p = new URLSearchParams({
    q: document.getElementById("f-q").value,
    game: document.getElementById("f-game").value,
    sentiment: document.getElementById("f-sentiment").value,
    voted: document.getElementById("f-voted").value,
    sort: document.getElementById("f-sort").value,
    page: state.page, per_page: 15,
  });
  return p.toString();
}

async function loadReviews() {
  const res = await fetch("/api/reviews?" + explorerParams());
  const data = await res.json();
  document.getElementById("explorer-meta").textContent =
    `${fmt(data.total)} matching reviews`;
  document.getElementById("reviews").innerHTML = data.results.map((r) => {
    const long = r.review_text_clean.length > 260;
    const shown = long ? r.review_text_clean.slice(0, 260) + "…" : r.review_text_clean;
    return `<div class="review">
      <div class="review-head">
        <span class="game">${r.game}</span>
        <span class="pill ${r.sentiment_label}">${r.sentiment_label} ${r.sentiment_score}</span>
        <span class="pill ${r.voted_up ? "vote-up" : "vote-down"}">
          ${r.voted_up ? "RECOMMENDED" : "NOT RECOMMENDED"}</span>
        <span class="meta">${r.date} · ${r.word_count} words ·
          ${fmt(Math.round(r.playtime_hours))}h played ·
          ${fmt(r.votes_up)} found helpful</span>
      </div>
      <div class="review-text ${long ? "collapsed" : ""}">${escapeHtml(shown)}</div>
      ${long ? `<button class="expand-btn" data-full="${encodeURIComponent(r.review_text_clean)}">show more</button>` : ""}
    </div>`;
  }).join("");
  document.getElementById("page-info").textContent =
    `page ${data.page} of ${data.pages}`;
  document.getElementById("prev").disabled = data.page <= 1;
  document.getElementById("next").disabled = data.page >= data.pages;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function wireExplorer(games) {
  const sel = document.getElementById("f-game");
  sel.innerHTML = '<option value="">All games</option>' +
    games.map((g) => `<option>${g.game}</option>`).join("");
  let debounce;
  document.getElementById("f-q").addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.page = 1; loadReviews(); }, 350);
  });
  for (const id of ["f-game", "f-sentiment", "f-voted", "f-sort"]) {
    document.getElementById(id).addEventListener("change",
      () => { state.page = 1; loadReviews(); });
  }
  document.getElementById("prev").addEventListener("click",
    () => { state.page--; loadReviews(); });
  document.getElementById("next").addEventListener("click",
    () => { state.page++; loadReviews(); });
  document.getElementById("reviews").addEventListener("click", (e) => {
    if (e.target.classList.contains("expand-btn")) {
      const div = e.target.previousElementSibling;
      if (e.target.textContent === "show more") {
        div.textContent = decodeURIComponent(e.target.dataset.full);
        div.classList.remove("collapsed");
        e.target.textContent = "show less";
      } else {
        div.textContent = div.textContent.slice(0, 260) + "…";
        div.classList.add("collapsed");
        e.target.textContent = "show more";
      }
    }
  });
}

(async function init() {
  const data = await loadSummary();
  chartData = data;
  const k = data.kpis;
  document.getElementById("data-badge").textContent =
    `${fmt(k.total_reviews)} reviews · synthetic demo data`;
  renderKpis(k);
  renderInsights(data.insights);
  renderCharts(data);
  renderGames(data.games);
  renderFunnel(data.cleaning_report);
  wireExplorer(data.games);
  await loadReviews();
})();
