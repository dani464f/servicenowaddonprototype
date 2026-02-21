import test from 'node:test';
import assert from 'node:assert/strict';
import { computeScores, classifyAndAction } from '../src/scoring.js';

test('classifies underpowered for high sustained pressure', () => {
  const scores = computeScores({
    gpu_util_p95: 96,
    vram_used_p95_pct: 98,
    cpu_util_p95: 92,
    ram_used_p95: 96,
    paging_pressure_minutes: 200,
    disk_latency_p95_ms: 120,
    disk_busy_minutes: 420,
    disk_queue_p95: 6,
    thermal_throttle_events: 8,
    active_minutes: 600,
    light_app_mix_factor: 0.1
  });
  const result = classifyAndAction(scores);
  assert.equal(result.classification, 'UNDERPOWERED');
  assert.equal(result.action, 'UPSIZE');
});

test('classifies overprovisioned for low stress + light workload', () => {
  const scores = computeScores({
    gpu_util_p95: 15,
    vram_used_p95_pct: 10,
    cpu_util_p95: 20,
    ram_used_p95: 35,
    paging_pressure_minutes: 0,
    disk_latency_p95_ms: 3,
    disk_busy_minutes: 12,
    disk_queue_p95: 0.2,
    thermal_throttle_events: 0,
    active_minutes: 30,
    light_app_mix_factor: 1.0
  });
  const result = classifyAndAction(scores);
  assert.equal(result.classification, 'OVERPROVISIONED');
  assert.equal(result.action, 'DOWNSIZE');
});
