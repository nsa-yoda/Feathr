import {
  MAX_HISTORY,
  appendBounded,
  createPoller,
  selectionInside,
  transformSnapshot,
} from './visualizer-core.js';

const d3 = window.d3;

const POLL_INTERVAL_MS = 500;
const STALE_AFTER_MS = 3000;
const CHART_HEIGHT = 220;
const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
let activeSession = null;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function formatNumber(value, digits = 1) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatLatency(value) {
  if (!value) return '—';
  return value < 1 ? `${Math.round(value * 1000)}ms` : `${value.toFixed(2)}s`;
}

function formatAge(timestamp) {
  if (!timestamp) return 'never';
  const seconds = Math.max(0, (Date.now() - timestamp) / 1000);
  return seconds < 1 ? `${Math.round(seconds * 1000)}ms ago` : `${seconds.toFixed(1)}s ago`;
}

function card(title, value, detail = '') {
  return `<article class="card visualizer-card"><h3>${esc(title)}</h3><div class="metric">${esc(value)}</div><div class="muted">${esc(detail)}</div></article>`;
}

function chartCard(id, title, description, footer = '') {
  return `<article class="card chart-card"><h3>${esc(title)}</h3><p class="muted chart-description">${esc(description)}</p><svg id="${id}" class="viz-chart" role="img" aria-label="${esc(title)}"></svg>${footer}</article>`;
}

function statusClass(state) {
  return state === 'healthy' ? 'good' : state === 'degraded' ? 'warn' : 'bad';
}

function renderHealth(health) {
  return Object.entries(health || {}).map(([name, value]) =>
    `<span class="health-pill ${statusClass(value.state)}"><span aria-hidden="true">●</span> ${esc(name.replaceAll('_', ' '))}: ${esc(value.state || 'unknown')}</span>`,
  ).join('');
}

function svgSize(node) {
  const width = Math.max(260, node.parentElement?.clientWidth || 640);
  return { width, height: CHART_HEIGHT, margin: { top: 14, right: 18, bottom: 32, left: 44 } };
}

function finishSvg(svg, size) {
  svg.attr('viewBox', `0 0 ${size.width} ${size.height}`).attr('width', size.width).attr('height', size.height);
}

function updateLineChart(selector, history, series, accessor) {
  const svg = d3.select(selector);
  if (svg.empty()) return;
  const size = svgSize(svg.node());
  finishSvg(svg, size);
  const { margin } = size;
  const innerWidth = size.width - margin.left - margin.right;
  const innerHeight = size.height - margin.top - margin.bottom;
  const x = d3.scaleTime().domain(d3.extent(history, (d) => new Date(d.timestamp)) || [new Date(), new Date()]).range([0, innerWidth]);
  const maxValue = Math.max(1, d3.max(history, (d) => d3.max(series, (name) => accessor(d, name))) || 1);
  const y = d3.scaleLinear().domain([0, maxValue * 1.1]).nice().range([innerHeight, 0]);
  const root = svg.selectAll('g.plot').data([null]).join('g').attr('class', 'plot').attr('transform', `translate(${margin.left},${margin.top})`);
  root.selectAll('g.x-axis').data([null]).join('g').attr('class', 'x-axis').attr('transform', `translate(0,${innerHeight})`).call(d3.axisBottom(x).ticks(4).tickFormat(d3.timeFormat('%H:%M:%S')));
  root.selectAll('g.y-axis').data([null]).join('g').attr('class', 'y-axis').call(d3.axisLeft(y).ticks(4));
  const line = d3.line().x((d) => x(new Date(d.timestamp))).y((d) => y(accessor(d, d.series))).defined((d) => Number.isFinite(accessor(d, d.series)));
  const paths = root.selectAll('path.series').data(series, (name) => name);
  paths.join(
    (enter) => enter.append('path').attr('class', 'series').attr('fill', 'none').attr('stroke-width', 2).attr('stroke', (name) => color(name)).attr('d', (name) => line(history.map((d) => ({ ...d, series: name })))),
    (update) => update.interrupt().transition().duration(reducedMotion() ? 0 : 180).attr('d', (name) => line(history.map((d) => ({ ...d, series: name })))),
    (exit) => exit.remove(),
  );
  const legend = svg.selectAll('g.legend').data([null]).join('g').attr('class', 'legend').attr('transform', `translate(${margin.left},8)`);
  legend.selectAll('text').data(series, (name) => name).join('text').attr('x', (_name, index) => index * 100).attr('fill', (name) => color(name)).text((name) => name);
}

function color(name) {
  return ({ received: '#1769aa', persisted: '#16794c', projected: '#7c3aed', retries: '#a15c00', dlq: '#b42318', depth: '#1769aa', oldestAge: '#a15c00', inFlight: '#7c3aed' })[name] || '#64748b';
}

function updateTypeChart(selector, types) {
  const svg = d3.select(selector);
  if (svg.empty()) return;
  const size = svgSize(svg.node());
  finishSvg(svg, size);
  const { margin } = size;
  const root = svg.selectAll('g.plot').data([null]).join('g').attr('class', 'plot').attr('transform', `translate(${margin.left},${margin.top})`);
  const width = size.width - margin.left - margin.right;
  const height = size.height - margin.top - margin.bottom;
  const x = d3.scaleBand().domain(types.map((d) => d.type)).range([0, width]).padding(0.18);
  const y = d3.scaleLinear().domain([0, Math.max(1, d3.max(types, (d) => d.count) || 1)]).nice().range([height, 0]);
  root.selectAll('g.x-axis').data([null]).join('g').attr('class', 'x-axis').attr('transform', `translate(0,${height})`).call(d3.axisBottom(x).tickFormat((value) => value.length > 12 ? `${value.slice(0, 11)}…` : value));
  root.selectAll('g.y-axis').data([null]).join('g').attr('class', 'y-axis').call(d3.axisLeft(y).ticks(4));
  root.selectAll('rect.bar').data(types, (d) => d.type).join(
    (enter) => enter.append('rect').attr('class', 'bar').attr('x', (d) => x(d.type)).attr('width', x.bandwidth()).attr('fill', '#1769aa').attr('y', height).attr('height', 0).call((selection) => selection.transition().duration(reducedMotion() ? 0 : 180).attr('y', (d) => y(d.count)).attr('height', (d) => height - y(d.count))),
    (update) => update.interrupt().transition().duration(reducedMotion() ? 0 : 180).attr('x', (d) => x(d.type)).attr('width', x.bandwidth()).attr('y', (d) => y(d.count)).attr('height', (d) => height - y(d.count)),
    (exit) => exit.remove(),
  );
}

function updateLatencyChart(selector, latency) {
  const svg = d3.select(selector);
  if (svg.empty()) return;
  const size = svgSize(svg.node());
  finishSvg(svg, size);
  const names = Object.keys(latency);
  const rows = names.flatMap((name) => (latency[name].buckets || []).filter((d) => d.bucket !== '+Inf').map((d) => ({ ...d, name })));
  const { margin } = size;
  const width = size.width - margin.left - margin.right;
  const height = size.height - margin.top - margin.bottom;
  const x = d3.scaleBand().domain([...new Set(rows.map((d) => d.bucket))]).range([0, width]).padding(0.16);
  const y = d3.scaleLinear().domain([0, Math.max(1, d3.max(rows, (d) => d.count) || 1)]).nice().range([height, 0]);
  const group = d3.scaleBand().domain(names).range([0, x.bandwidth()]).padding(0.04);
  const root = svg.selectAll('g.plot').data([null]).join('g').attr('class', 'plot').attr('transform', `translate(${margin.left},${margin.top})`);
  root.selectAll('g.x-axis').data([null]).join('g').attr('class', 'x-axis').attr('transform', `translate(0,${height})`).call(d3.axisBottom(x).tickFormat((value) => `${value}s`));
  root.selectAll('g.y-axis').data([null]).join('g').attr('class', 'y-axis').call(d3.axisLeft(y).ticks(4));
  root.selectAll('g.latency-group').data(rows, (d) => `${d.name}:${d.bucket}`).join(
    (enter) => enter.append('g').attr('class', 'latency-group').call((selection) => selection.append('rect').attr('x', (d) => x(d.bucket) + group(d.name)).attr('width', group.bandwidth()).attr('fill', (d) => color(d.name)).attr('y', height).attr('height', 0).transition().duration(reducedMotion() ? 0 : 180).attr('y', (d) => y(d.count)).attr('height', (d) => height - y(d.count))),
    (update) => update.select('rect').interrupt().transition().duration(reducedMotion() ? 0 : 180).attr('x', (d) => x(d.bucket) + group(d.name)).attr('width', group.bandwidth()).attr('y', (d) => y(d.count)).attr('height', (d) => height - y(d.count)),
    (exit) => exit.remove(),
  );
  svg.selectAll('g.legend').data([null]).join('g').attr('class', 'legend').attr('transform', `translate(${margin.left},8)`).selectAll('text').data(names).join('text').attr('x', (_name, index) => index * 84).attr('fill', (name) => color(name)).text((name) => name);
}

function visualizerView() {
  cleanupVisualizer();
  const app = document.getElementById('app');
  app.innerHTML = `<section class="view visualizer-view"><div class="visualizer-heading"><div><h2>Visualizer</h2><p class="lede">Live operational and analytics signals from the running platform.</p></div><div id="visualizer-live" class="live-indicator warn" role="status">Connecting…</div></div><div id="visualizer-health" class="health-row"></div><div id="visualizer-cards" class="grid"></div><div class="chart-grid">${chartCard('throughput-chart', 'Event throughput', 'Events per second over the bounded five-minute window.')}${chartCard('type-chart', 'Events by type', 'Current realtime distribution from canonical analytics.')}${chartCard('queue-chart', 'Queue health', 'Depth, in-flight messages, and oldest-message age.')}${chartCard('latency-chart', 'Dependency latency buckets', 'Bounded histogram buckets exported by the lightweight metrics registry.')}<article class="card chart-card latency-summary-card"><h3>Latency percentiles</h3><p class="muted chart-description">Calculated from the exported bounded histogram buckets.</p><div id="latency-summary"></div></article></div><div id="visualizer-message" class="notice" role="status">Waiting for the first operational snapshot…</div></section>`;
  const session = { active: true, staleTimer: null, previous: null, latest: null, history: [], poller: null, pendingSnapshot: null, root: app.querySelector('.visualizer-view') };
  activeSession = session;
  window.__feathrVisualizerCleanup = cleanupVisualizer;
  const request = window.__feathrConsole.request;
  const setLive = (text, className) => { const node = document.getElementById('visualizer-live'); if (node) { node.textContent = text; node.className = `live-indicator ${className}`; } };
  const setMessage = (text, error = false) => { const node = document.getElementById('visualizer-message'); if (node) { node.textContent = text; node.className = `notice${error ? ' error' : ''}`; } };
  const hasSelection = () => selectionInside(window.getSelection?.(), session.root);
  const updateAge = () => { if (!session.active || !session.latest || hasSelection()) return; const age = Date.now() - session.latest.receivedAt; if (age > STALE_AFTER_MS) setLive(`Stale • last update ${formatAge(session.latest.receivedAt)}`, 'warn'); else setLive(`Live • updated ${formatAge(session.latest.receivedAt)}`, 'good'); };
  const applySnapshot = (snapshot) => {
    if (!session.active) return;
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const sample = transformSnapshot(snapshot, session.previous);
    session.previous = sample;
    session.history = appendBounded(session.history, sample, MAX_HISTORY);
    session.latest = { ...sample, receivedAt: Date.now(), snapshot };
    const q = sample.queue;
    document.getElementById('visualizer-cards').innerHTML = [
      card('Queue depth', formatNumber(q.depth, 0), `${formatNumber(q.inFlight, 0)} in flight`),
      card('Oldest message', formatLatency(q.oldestAge), 'queue age'),
      card('Projection lag', formatLatency(q.projectionLag), 'Elasticsearch checkpoint'),
      card('Throughput', `${formatNumber(sample.rates.received, 1)}/s`, 'accepted HTTP events'),
      card('Retries / DLQ', `${formatNumber(sample.counters.retries, 0)} / ${formatNumber(sample.counters.dlq, 0)}`, 'cumulative worker counters'),
      card('Cache hit rate', `${formatNumber(sample.cache.hitRate * 100, 1)}%`, `${sample.cache.hits} hits / ${sample.cache.misses} misses`),
      card('Worker latency p95', formatLatency(sample.latencies.worker.p95), 'bounded histogram'),
      card('Search latency p95', formatLatency(sample.latencies.elasticsearch.p95), 'bounded histogram'),
    ].join('');
    document.getElementById('visualizer-health').innerHTML = renderHealth(sample.health);
    updateLineChart('#throughput-chart', session.history, ['received', 'persisted', 'projected', 'retries'], (d, key) => d.rates[key]);
    updateTypeChart('#type-chart', sample.types);
    updateLineChart('#queue-chart', session.history, ['depth', 'oldestAge', 'inFlight'], (d, key) => d.queue[key]);
    updateLatencyChart('#latency-chart', sample.latencies);
    document.getElementById('latency-summary').innerHTML = `<table class="latency-table"><thead><tr><th>Dependency</th><th>p50</th><th>p95</th><th>p99</th></tr></thead><tbody>${Object.entries(sample.latencies).map(([name, value]) => `<tr><td>${esc(name)}</td><td>${esc(formatLatency(value.p50))}</td><td>${esc(formatLatency(value.p95))}</td><td>${esc(formatLatency(value.p99))}</td></tr>`).join('')}</tbody></table>`;
    setLive('Live • updated now', 'good');
    setMessage(`Snapshot ${new Date(sample.timestamp).toLocaleTimeString()} • ${snapshot.realtime_cache || 'metrics'} cache`);
    // Card text can change width/height between samples. Restore the viewport
    // anchor after the stable view updates so polling never scrolls the page.
    window.scrollTo(scrollX, scrollY);
  };
  const flushPending = () => {
    if (session.pendingSnapshot && !hasSelection()) {
      const snapshot = session.pendingSnapshot;
      session.pendingSnapshot = null;
      applySnapshot(snapshot);
    }
  };
  const update = (snapshot) => {
    if (hasSelection()) {
      // Keep the latest data without touching the selected DOM range. The
      // selectionchange handler applies one coalesced repaint after release.
      session.pendingSnapshot = snapshot;
      return;
    }
    applySnapshot(snapshot);
  };
  session.poller = createPoller({
    interval: POLL_INTERVAL_MS,
    fetchSnapshot: (signal) => request('/operations/visualizer?window_minutes=5', { signal }).then(({ body }) => body),
    onData: update,
    onError: (error) => {
      if (hasSelection()) return;
      setLive(`Stale • last update ${formatAge(session.latest?.receivedAt)}`, 'warn');
      setMessage('Operational snapshot unavailable; retaining the last successful charts.', true);
    },
    isHidden: () => document.hidden,
  });
  const onVisibility = () => { if (document.hidden) session.poller.pause(); else session.poller.resume(); };
  document.addEventListener('visibilitychange', onVisibility);
  session.removeVisibility = () => document.removeEventListener('visibilitychange', onVisibility);
  document.addEventListener('selectionchange', flushPending);
  session.removeSelection = () => document.removeEventListener('selectionchange', flushPending);
  session.resize = new ResizeObserver(() => { if (!session.latest || hasSelection()) return; updateLineChart('#throughput-chart', session.history, ['received', 'persisted', 'projected', 'retries'], (d, key) => d.rates[key]); updateTypeChart('#type-chart', session.latest.types); updateLineChart('#queue-chart', session.history, ['depth', 'oldestAge', 'inFlight'], (d, key) => d.queue[key]); updateLatencyChart('#latency-chart', session.latest.latencies); });
  document.querySelectorAll('.viz-chart').forEach((node) => session.resize.observe(node.parentElement));
  session.staleTimer = window.setInterval(updateAge, 1000);
  session.poller.start();
}

function cleanupVisualizer() {
  if (!activeSession) return;
  activeSession.active = false;
  if (activeSession.staleTimer) clearInterval(activeSession.staleTimer);
  activeSession.poller?.stop();
  activeSession.removeVisibility?.();
  activeSession.resize?.disconnect();
  activeSession.removeSelection?.();
  activeSession = null;
  window.__feathrVisualizerCleanup = null;
}

window.__feathrVisualizerView = visualizerView;
window.__feathrVisualizerCleanup = cleanupVisualizer;
window.__feathrVisualizerTesting = { transformSnapshot, appendBounded, selectionInside, MAX_HISTORY, POLL_INTERVAL_MS };
