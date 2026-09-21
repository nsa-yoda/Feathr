const MAX_HISTORY = 600;

export function parseMetrics(text) {
  const values = {};
  for (const line of String(text || '').split('\n')) {
    const match = line.match(/^([a-z][a-z0-9_]*)(?:\{([^}]*)\})?\s+([-+0-9.eE]+)$/);
    if (!match) continue;
    const labels = {};
    for (const part of (match[2] || '').split(',').filter(Boolean)) {
      const pair = part.split('=', 2);
      if (pair.length === 2) labels[pair[0]] = pair[1].replace(/^"|"$/g, '');
    }
    (values[match[1]] ||= []).push({ labels, value: Number(match[3]) });
  }
  return values;
}

export function metricValue(parsed, name, labels = {}) {
  const row = (parsed[name] || []).find((item) =>
    Object.entries(labels).every(([key, value]) => item.labels[key] === value),
  );
  return row ? row.value : 0;
}

function counter(parsed, name, labels) {
  return metricValue(parsed, name, labels);
}

function rate(current, previous, elapsedSeconds) {
  if (previous === undefined) return 0;
  return Math.max(0, current - previous) / Math.max(elapsedSeconds, 0.001);
}

function histogram(parsed, name, labels = {}) {
  return (parsed[`${name}_bucket`] || [])
    .filter((row) => Object.entries(labels).every(([key, value]) => row.labels[key] === value))
    .map((row) => ({ bucket: row.labels.le, count: row.value }));
}

export function appendBounded(history, sample, max = MAX_HISTORY) {
  const next = history.concat(sample);
  return next.length > max ? next.slice(next.length - max) : next;
}

/**
 * Return true when the user has a non-collapsed selection inside the view.
 * Replacing selected DOM nodes collapses the browser range, so callers should
 * defer repainting until the selection is released.
 */
export function selectionInside(selection, root) {
  if (!selection || selection.isCollapsed || !selection.rangeCount || !root) return false;
  const range = selection.getRangeAt(0);
  const node = range.commonAncestorContainer || selection.anchorNode;
  return Boolean(node && (node === root || root.contains?.(node)));
}

export function createPoller({
  interval = 500,
  fetchSnapshot,
  onData,
  onError,
  isHidden = () => false,
}) {
  let active = false;
  let paused = false;
  let busy = false;
  let timer = null;
  let controller = null;

  const schedule = () => {
    if (active && !paused && !isHidden()) timer = setTimeout(poll, interval);
  };
  const poll = async () => {
    if (!active || paused || isHidden() || busy) return;
    busy = true;
    controller = new AbortController();
    try {
      const snapshot = await fetchSnapshot(controller.signal);
      if (active) onData(snapshot);
    } catch (error) {
      if (active && error?.name !== 'AbortError') onError(error);
    } finally {
      busy = false;
      controller = null;
      schedule();
    }
  };
  return {
    start() { active = true; void poll(); },
    stop() { active = false; if (timer) clearTimeout(timer); controller?.abort(); timer = null; },
    pause() { paused = true; if (timer) clearTimeout(timer); controller?.abort(); timer = null; },
    resume() { paused = false; if (active) void poll(); },
    get busy() { return busy; },
  };
}

export function transformSnapshot(snapshot, previous = null, now = Date.now()) {
  const parsed = parseMetrics(snapshot?.metrics);
  const previousCounters = previous?.counters || {};
  const elapsed = previous ? Math.max((now - previous.timestamp) / 1000, 0.001) : 0.5;
  const counters = {
    received: counter(parsed, 'event_platform_http_requests_total', { method: 'POST', route: 'events' }),
    persisted: counter(parsed, 'event_platform_worker_operations_total', { outcome: 'inserted' }),
    projected: counter(parsed, 'event_platform_elasticsearch_operations_total', { outcome: 'success' }),
    retries: counter(parsed, 'event_platform_worker_operations_total', { outcome: 'retry' }),
    dlq: counter(parsed, 'event_platform_worker_operations_total', { outcome: 'dlq' }),
    cacheHits: counter(parsed, 'event_platform_cache_operations_total', { outcome: 'hit' }),
    cacheMisses: counter(parsed, 'event_platform_cache_operations_total', { outcome: 'miss' }),
  };
  const latencies = {};
  for (const [label, name] of Object.entries({
    request: 'event_platform_request_latency_seconds',
    worker: 'event_platform_worker_processing_latency_seconds',
    mongo: 'event_platform_mongo_operation_latency_seconds',
    elasticsearch: 'event_platform_elasticsearch_operation_latency_seconds',
    redis: 'event_platform_redis_operation_latency_seconds',
  })) {
    const buckets = histogram(parsed, name);
    const count = metricValue(parsed, `${name}_count`);
    const sum = metricValue(parsed, `${name}_sum`);
    latencies[label] = {
      buckets,
      count,
      average: count ? sum / count : 0,
      p50: percentileBucket(buckets, count * 0.5),
      p95: percentileBucket(buckets, count * 0.95),
      p99: percentileBucket(buckets, count * 0.99),
    };
  }
  return {
    timestamp: now,
    counters,
    rates: Object.fromEntries(Object.entries(counters).map(([key, value]) => [key, rate(value, previousCounters[key], elapsed)])),
    queue: {
      depth: metricValue(parsed, 'event_platform_queue_depth'),
      inFlight: metricValue(parsed, 'event_platform_queue_in_flight'),
      oldestAge: metricValue(parsed, 'event_platform_queue_oldest_age_seconds'),
      workerActive: metricValue(parsed, 'event_platform_worker_active'),
      projectionLag: metricValue(parsed, 'event_platform_projection_lag_seconds'),
    },
    latencies,
    cache: {
      hits: counters.cacheHits,
      misses: counters.cacheMisses,
      hitRate: counters.cacheHits + counters.cacheMisses
        ? counters.cacheHits / (counters.cacheHits + counters.cacheMisses)
        : 0,
    },
    types: Object.entries(snapshot?.realtime?.by_event_type || {})
      .map(([type, count]) => ({ type, count: Number(count) || 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12),
    health: snapshot?.health?.components || {},
  };
}

function percentileBucket(buckets, target) {
  if (!buckets.length || target <= 0) return 0;
  const row = buckets.find((item) => item.count >= target);
  return row ? (row.bucket === '+Inf' ? 10 : Number(row.bucket)) : 10;
}

export { MAX_HISTORY };
