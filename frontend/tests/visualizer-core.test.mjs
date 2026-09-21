import test from 'node:test';
import assert from 'node:assert/strict';

import {
  MAX_HISTORY,
  appendBounded,
  createPoller,
  parseMetrics,
  transformSnapshot,
} from '../public/visualizer-core.js';

const metrics = (received, cacheHits = 2) => `
event_platform_http_requests_total{method="POST",route="events",status="2xx"} ${received}
event_platform_worker_operations_total{outcome="inserted"} 4
event_platform_worker_operations_total{outcome="retry"} 1
event_platform_worker_operations_total{outcome="dlq"} 0
event_platform_elasticsearch_operations_total{outcome="success"} 3
event_platform_cache_operations_total{outcome="hit"} ${cacheHits}
event_platform_cache_operations_total{outcome="miss"} 1
event_platform_queue_depth 7
event_platform_queue_in_flight 2
event_platform_queue_oldest_age_seconds 1.25
event_platform_worker_active 1
event_platform_projection_lag_seconds 0.4
event_platform_request_latency_seconds_bucket{le="0.1"} 1
event_platform_request_latency_seconds_bucket{le="1"} 2
event_platform_request_latency_seconds_bucket{le="+Inf"} 2
event_platform_request_latency_seconds_count 2
event_platform_request_latency_seconds_sum 0.3
`;

test('parses bounded metrics and transforms realtime state', () => {
  const parsed = parseMetrics(metrics(10));
  const first = transformSnapshot({ metrics: metrics(10), realtime: { by_event_type: { click: 3 } } }, null, 1000);
  const second = transformSnapshot({ metrics: metrics(14, 4), realtime: { by_event_type: { click: 4 } } }, first, 1500);
  assert.equal(parsed.event_platform_queue_depth[0].value, 7);
  assert.equal(second.rates.received, 8);
  assert.equal(second.queue.oldestAge, 1.25);
  assert.equal(second.cache.hitRate, 4 / 5);
  assert.equal(second.types[0].type, 'click');
  assert.equal(second.latencies.request.p50, 0.1);
});

test('rolling history is bounded to the visible retention window', () => {
  const history = appendBounded([], 0, 3);
  const bounded = appendBounded(appendBounded(appendBounded(history, 1, 3), 2, 3), 3, 3);
  assert.equal(MAX_HISTORY, 600);
  assert.deepEqual(bounded, [1, 2, 3]);
});

test('poller never overlaps requests and stops scheduling after cancellation', async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  let calls = 0;
  let resolveRequest;
  const poller = createPoller({
    interval: 5,
    fetchSnapshot: () => {
      calls += 1;
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      return new Promise((resolve) => { resolveRequest = () => { inFlight -= 1; resolve({ calls }); }; });
    },
    onData: () => {},
    onError: () => {},
  });
  poller.start();
  await new Promise((resolve) => setTimeout(resolve, 2));
  assert.equal(poller.busy, true);
  resolveRequest();
  await new Promise((resolve) => setTimeout(resolve, 8));
  assert.equal(maxInFlight, 1);
  poller.stop();
  const callsAtStop = calls;
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(calls, callsAtStop);
});

test('poller pauses while hidden and resumes immediately when visible', async () => {
  let hidden = true;
  let calls = 0;
  const poller = createPoller({
    interval: 5,
    fetchSnapshot: async () => { calls += 1; return {}; },
    onData: () => {},
    onError: () => {},
    isHidden: () => hidden,
  });
  poller.start();
  await new Promise((resolve) => setTimeout(resolve, 8));
  assert.equal(calls, 0);
  hidden = false;
  poller.resume();
  await new Promise((resolve) => setTimeout(resolve, 2));
  assert.equal(calls, 1);
  poller.stop();
});
