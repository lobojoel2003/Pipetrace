// Address search box with suggestions (ARIA 1.2 combobox pattern).
// On the live site suggestions come from /api/search/. In a static export the
// whole index is loaded once and searched here, using the same normalisation and
// scoring as pipetrace/inventory/addresses.py.
import { CODE_CLASS, escapeHtml, shapeSvg } from "./shapes.js";

let indexPromise = null;

function loadIndex(config) {
  if (!indexPromise) {
    indexPromise = fetch(config.searchIndex)
      .then((response) => {
        if (!response.ok) throw new Error(`search index: HTTP ${response.status}`);
        return response.json();
      })
      .then((data) => prepareIndex(data));
  }
  return indexPromise;
}

function prepareIndex(data) {
  const abbr = data.config.abbr;
  const expansions = {};
  for (const [word, short] of Object.entries(abbr)) {
    (expansions[short] ||= []).push(word);
  }
  const matcher = {
    abbr,
    expansions,
    units: new Set(data.config.units),
    noise: new Set(data.config.noise),
  };
  const lines = data.lines.map(([id, address, city, normalized, code]) => ({
    id, address, city, normalized, code, tokens: normalized.split(" "),
  }));
  return { matcher, lines };
}

function stripAccents(text) {
  return text.normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

export function tokens(text, m) {
  if (!text) return [];
  let value = stripAccents(String(text)).toUpperCase().replace(/&/g, " AND ");
  value = value.replace(/#/g, " # ").replace(/[^\p{L}\p{N}_#/\- ]+/gu, " ");
  const raw = value.split(/\s+/).map((t) => t.replace(/^[-/]+|[-/]+$/g, "")).filter(Boolean);
  const out = [];
  raw.forEach((token, i) => {
    if (m.noise.has(token)) return;
    if (m.units.has(token) && (i > 0 || token !== "NO")) {
      if (out[out.length - 1] !== "#") out.push("#");
      return;
    }
    if (token === "#" && out[out.length - 1] === "#") return;
    out.push(m.abbr[token] || token);
  });
  return out;
}

export function streetLine(query) {
  let text = (query || "").trim();
  if (text.includes(",")) text = text.split(",", 1)[0];
  return text.replace(/\b\d{5}(?:-\d{4})?$/, "").trim();
}

function editDistanceAtMostOne(a, b) {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) {
    const diffs = [];
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diffs.push(i);
    if (diffs.length === 1) return true;
    return diffs.length === 2 && diffs[1] === diffs[0] + 1
      && a[diffs[0]] === b[diffs[1]] && a[diffs[1]] === b[diffs[0]];
  }
  if (a.length > b.length) [a, b] = [b, a];
  let i = 0, j = 0, skipped = false;
  while (i < a.length && j < b.length) {
    if (a[i] !== b[j]) {
      if (skipped) return false;
      skipped = true;
      j++;
      continue;
    }
    i++; j++;
  }
  return true;
}

// Mirrors addresses.score() in Python.
export function scoreTokens(q, c, m) {
  if (!q.length || !c.length) return 0;
  let total = 0;
  const used = new Set();
  const last = q.length - 1;
  for (let qi = 0; qi < q.length; qi++) {
    const token = q[qi];
    let best = 0, bestIdx = -1;
    for (let ci = 0; ci < c.length; ci++) {
      if (used.has(ci)) continue;
      const cand = c[ci];
      const isNumber = /^\d/.test(token);
      const forms = [cand, ...(m.expansions[cand] || [])];
      let s;
      if (token === cand) s = isNumber ? 3 : 2;
      else if (qi === last && forms.some((f) => f.startsWith(token))) s = isNumber ? 1 : 1.5;
      else if (!isNumber && token.length >= 4 && forms.some((f) => editDistanceAtMostOne(token, f))) s = 1;
      else continue;
      if (ci === qi) s += 0.25;
      if (s > best) { best = s; bestIdx = ci; }
    }
    if (bestIdx < 0) return 0;
    used.add(bestIdx);
    total += best;
  }
  return total - 0.05 * (c.length - used.size);
}

export function searchIndex(index, query, limit = 8) {
  const q = tokens(streetLine(query), index.matcher);
  if (!q.length) return [];
  const results = rank(index, q, limit);
  // A house number that isn't in the inventory: offer the rest of that street.
  if (!results.length && q.length > 1 && /^\d/.test(q[0])) return rank(index, q.slice(1), limit);
  return results;
}

function rank(index, q, limit) {
  const normalized = q.join(" ");
  const results = [];
  for (const line of index.lines) {
    const score = scoreTokens(q, line.tokens, index.matcher);
    if (score <= 0) continue;
    const exact = line.normalized === normalized || line.normalized.startsWith(`${normalized} #`);
    results.push({ ...line, score: score + (exact ? 5 : 0), exact });
  }
  results.sort((a, b) => b.score - a.score || a.normalized.localeCompare(b.normalized, undefined, { numeric: true }));
  return results.slice(0, limit);
}

async function fetchResults(config, query, limit = 8) {
  if (config.static) {
    const index = await loadIndex(config);
    return searchIndex(index, query, limit).map((r) => ({
      id: r.id,
      address: r.address,
      city: r.city,
      code: r.code,
      label: config.labels.status[r.code],
      url: config.lineUrl.replace("__ID__", r.id),
      exact: r.exact,
    }));
  }
  const url = `${config.searchApi}?q=${encodeURIComponent(query)}&lang=${config.lang}`;
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`search: HTTP ${response.status}`);
  return (await response.json()).results;
}

function optionHtml(result, id) {
  const cls = CODE_CLASS[result.code] || "unknown";
  return `<li role="option" id="${id}" data-url="${escapeHtml(result.url)}" aria-selected="false">`
    + `${shapeSvg(result.code, 18)}<span class="addr">${escapeHtml(result.address)}`
    + `${result.city ? `<span class="city">, ${escapeHtml(result.city)}</span>` : ""}</span>`
    + `<span class="chip chip-${cls}">${escapeHtml(result.label)}</span></li>`;
}

function resultCount(config, n) {
  return n === 1 ? config.labels.oneResult : config.labels.results.replace("%(count)s", n);
}

function setup(form, config) {
  const input = form.querySelector('input[type="search"]');
  const list = form.querySelector('[role="listbox"]');
  const status = form.querySelector("[data-search-status]");
  if (!input || !list) return;
  let results = [];
  let active = -1;
  let timer = null;
  let seq = 0;

  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };

  const highlight = (index) => {
    const options = [...list.querySelectorAll('[role="option"]')];
    options.forEach((el, i) => el.setAttribute("aria-selected", i === index ? "true" : "false"));
    active = index;
    if (options[index]) {
      input.setAttribute("aria-activedescendant", options[index].id);
      options[index].scrollIntoView({ block: "nearest" });
    }
  };

  const render = () => {
    if (!results.length) {
      list.innerHTML = `<li class="empty" role="presentation">${escapeHtml(config.labels.noResults)}</li>`;
    } else {
      list.innerHTML = results.map((r, i) => optionHtml(r, `${list.id}-opt-${i}`)).join("");
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (status) status.textContent = results.length ? resultCount(config, results.length) : config.labels.noResults;
    active = -1;
  };

  const update = async () => {
    const query = input.value.trim();
    if (query.length < 2) { results = []; close(); return; }
    const mine = ++seq;
    try {
      const found = await fetchResults(config, query);
      if (mine !== seq) return;
      results = found;
      render();
    } catch (error) {
      console.error(error);
      close();
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(update, config.static ? 60 : 160);
  });
  input.addEventListener("focus", () => { if (config.static) loadIndex(config).catch(() => {}); });
  input.addEventListener("keydown", (event) => {
    const count = list.querySelectorAll('[role="option"]').length;
    if (event.key === "ArrowDown" && count) {
      event.preventDefault();
      if (list.hidden) render();
      highlight((active + 1) % count);
    } else if (event.key === "ArrowUp" && count) {
      event.preventDefault();
      highlight(active <= 0 ? count - 1 : active - 1);
    } else if (event.key === "Escape") {
      close();
    } else if (event.key === "Enter" && active >= 0 && results[active]) {
      event.preventDefault();
      window.location.href = results[active].url;
    }
  });
  list.addEventListener("mousedown", (event) => event.preventDefault());
  list.addEventListener("click", (event) => {
    const option = event.target.closest('[role="option"]');
    if (option) window.location.href = option.dataset.url;
  });
  input.addEventListener("blur", () => setTimeout(close, 120));

  form.addEventListener("submit", async (event) => {
    if (!config.static) return; // the server handles it
    event.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    const found = await fetchResults(config, query);
    const exact = found.filter((r) => r.exact);
    if (exact.length === 1) {
      window.location.href = exact[0].url;
      return;
    }
    window.location.href = `${config.searchPage}?q=${encodeURIComponent(query)}`;
  });
}

async function renderStaticResults(config) {
  const container = document.querySelector("[data-search-results]");
  if (!container || !config.static) return;
  const query = new URLSearchParams(window.location.search).get("q") || "";
  const input = document.querySelector('form[data-search] input[type="search"]');
  if (input && query) input.value = query;
  if (!query) return;
  const results = await fetchResults(config, query, 25);
  if (!results.length) {
    container.innerHTML = `<div class="callout"><p class="mb-0">${escapeHtml(config.labels.noResults)}</p></div>`;
    return;
  }
  const items = results.map((r) => {
    const cls = CODE_CLASS[r.code] || "unknown";
    return `<li><a href="${escapeHtml(r.url)}">${shapeSvg(r.code, 18)}<span class="addr">${escapeHtml(r.address)}`
      + `${r.city ? `<span class="muted">, ${escapeHtml(r.city)}</span>` : ""}</span>`
      + `<span class="chip chip-${cls}">${escapeHtml(r.label)}</span></a></li>`;
  }).join("");
  container.innerHTML = `<h2 style="font-size:1.1rem">${escapeHtml(resultCount(config, results.length))}</h2><ul class="result-list">${items}</ul>`;
}

export function initSearch(config) {
  document.querySelectorAll("form[data-search]").forEach((form) => setup(form, config));
  renderStaticResults(config).catch((error) => console.error(error));
}

// Lets static-site forms find the line for ?line=<id>.
export async function findLine(config, id) {
  const index = await loadIndex(config);
  return index.lines.find((line) => line.id === id) || null;
}
