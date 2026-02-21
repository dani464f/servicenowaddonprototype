import { computeScores, classifyAndAction } from '../../src/scoring.js';
import crypto from 'node:crypto';

const db = {
  ingested: new Set(),
  telemetry: new Map(),
  policies: new Map(),
  recommendations: new Map()
};

function json(statusCode, body) {
  return { statusCode, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) };
}

function parse(event) {
  try { return event.body ? JSON.parse(event.body) : {}; } catch { return null; }
}

function quantile95(arr) {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const i = Math.floor(0.95 * (sorted.length - 1));
  return sorted[i];
}

function getPathParts(path) {
  const normalized = path.replace(/^\/.netlify\/functions\/api\/?/, '').replace(/^api\/?/, '').replace(/^\//, '');
  return normalized.split('/').filter(Boolean);
}

function ensureTenant(tenantId) {
  if (!db.telemetry.has(tenantId)) db.telemetry.set(tenantId, []);
}

function createRecommendations(tenant_id) {
  const records = db.telemetry.get(tenant_id) || [];
  const byDevice = new Map();
  for (const r of records) {
    if (!byDevice.has(r.device_key)) byDevice.set(r.device_key, []);
    byDevice.get(r.device_key).push(r);
  }

  const results = [];
  for (const [device_key, recs] of byDevice.entries()) {
    const appMinutes = recs.flatMap(r => r.apps || []);
    const totalAppMinutes = appMinutes.reduce((a, b) => a + (b.active_minutes || 0), 0) || 1;
    const heavyCategories = new Set(['CAD', 'ML', 'VIDEO', 'IDE', 'BI']);
    const heavyMinutes = appMinutes
      .filter(a => heavyCategories.has(String(a.category || '').toUpperCase()))
      .reduce((a, b) => a + (b.active_minutes || 0), 0);

    const signals = {
      gpu_util_p95: quantile95(recs.map(x => x.gpu?.util_pct || 0)),
      vram_used_p95_pct: quantile95(recs.map(x => Math.min(100, ((x.gpu?.vram_used_mb || 0) / 8192) * 100))),
      cpu_util_p95: quantile95(recs.map(x => x.cpu?.util_pct || 0)),
      ram_used_p95: quantile95(recs.map(x => x.ram?.used_pct || 0)),
      paging_pressure_minutes: recs.reduce((a, x) => a + (x.ram?.paging_pressure || 0), 0),
      disk_latency_p95_ms: quantile95(recs.map(x => x.disk?.latency_ms || 0)),
      disk_busy_minutes: recs.reduce((a, x) => a + (((x.disk?.busy_pct || 0) / 100) * 5), 0),
      disk_queue_p95: quantile95(recs.map(x => x.disk?.queue_len || 0)),
      thermal_throttle_events: recs.filter(x => x.thermal?.throttle_event).length,
      active_minutes: recs.reduce((a, x) => a + (x.gpu?.active_minutes || 0), 0),
      light_app_mix_factor: Math.max(0, Math.min(1, 1 - heavyMinutes / totalAppMinutes))
    };

    const scores = computeScores(signals);
    const { classification, action } = classifyAndAction(scores);
    const confidence = action === 'DOWNSIZE' && scores.overprov > 80 ? 0.9 : (classification === 'RIGHT_SIZED' ? 0.7 : 0.85);

    const recommendation = {
      recommendation_id: crypto.randomUUID(),
      tenant_id,
      device_key,
      run_date: new Date().toISOString().slice(0, 10),
      classification,
      action,
      confidence,
      workload_fit_score: Number(scores.fit.toFixed(2)),
      overprovision_score: Number(scores.overprov.toFixed(2)),
      expected_savings_usd_annual: action === 'DOWNSIZE' ? 1200 : 0,
      risk_flags: signals.thermal_throttle_events > 3 ? ['THERMAL'] : [],
      top_reasons: [
        `GPU pressure=${scores.gpu_pressure.toFixed(2)}`,
        `RAM pressure=${scores.ram_pressure.toFixed(2)}`,
        `Disk score=${scores.disk_score.toFixed(2)}`
      ],
      status: action === 'EXTEND_LIFE' ? 'NO_ACTION' : 'PENDING'
    };

    db.recommendations.set(recommendation.recommendation_id, recommendation);
    results.push(recommendation);
  }

  return results;
}

export async function handler(event) {
  const method = event.httpMethod;
  const parts = getPathParts(event.path || '');

  if (method === 'GET' && parts.length === 1 && parts[0] === 'healthz') {
    return json(200, { status: 'ok' });
  }

  if (method === 'POST' && parts[0] === 'v1' && parts[1] === 'ingestion' && parts[2] === 'telemetry-batch') {
    const body = parse(event);
    if (!body) return json(400, { error: 'invalid_json' });
    const key = `${body.tenant_id}|${body.source}|${body.batch_id}`;
    if (db.ingested.has(key)) return json(200, { status: 'duplicate', tenant_id: body.tenant_id, accepted_records: 0, deduped: true });
    db.ingested.add(key);
    ensureTenant(body.tenant_id);
    const incoming = body.records || [];
    db.telemetry.set(body.tenant_id, [...db.telemetry.get(body.tenant_id), ...incoming]);
    return json(200, { status: 'accepted', tenant_id: body.tenant_id, accepted_records: incoming.length, deduped: false });
  }

  if (method === 'POST' && parts[0] === 'v1' && parts[1] === 'admin' && parts[2] === 'policies' && parts.length === 3) {
    const body = parse(event);
    if (!body) return json(400, { error: 'invalid_json' });
    const policy = {
      policy_id: crypto.randomUUID(),
      tenant_id: body.tenant_id,
      name: body.name,
      strict_mode: !!body.strict_mode,
      thresholds: body.thresholds || {},
      auto_execute_rules: body.auto_execute_rules || {},
      effective_from: new Date().toISOString(),
      effective_to: null
    };
    db.policies.set(policy.policy_id, policy);
    return json(200, policy);
  }

  if (parts[0] === 'v1' && parts[1] === 'admin' && parts[2] === 'policies' && parts[3]) {
    const policyId = parts[3];
    const policy = db.policies.get(policyId);
    if (!policy) return json(404, { error: 'policy_not_found' });

    if (method === 'GET' && parts.length === 4) return json(200, policy);

    if (method === 'PATCH' && parts.length === 4) {
      const patch = parse(event);
      if (!patch) return json(400, { error: 'invalid_json' });
      const updated = { ...policy, ...patch };
      db.policies.set(policyId, updated);
      return json(200, updated);
    }

    if (method === 'POST' && parts[4] === 'simulate') {
      const payload = parse(event);
      if (!payload) return json(400, { error: 'invalid_json' });
      return json(200, { items: createRecommendations(payload.tenant_id) });
    }
  }

  if (method === 'GET' && parts[0] === 'v1' && parts[1] === 'recommendations' && parts.length === 2) {
    const tenant_id = event.queryStringParameters?.tenant_id;
    let items = [...db.recommendations.values()];
    if (tenant_id) items = items.filter(x => x.tenant_id === tenant_id);
    const action = event.queryStringParameters?.action;
    if (action) items = items.filter(x => x.action === action);
    const classification = event.queryStringParameters?.classification;
    if (classification) items = items.filter(x => x.classification === classification);
    return json(200, { items });
  }

  if (parts[0] === 'v1' && parts[1] === 'recommendations' && parts[2]) {
    const recommendation_id = parts[2];
    const recommendation = db.recommendations.get(recommendation_id);
    if (!recommendation) return json(404, { error: 'recommendation_not_found' });

    if (method === 'GET' && parts.length === 3) return json(200, recommendation);
    if (method === 'POST' && parts[3] === 'approve') {
      recommendation.status = 'APPROVED';
      db.recommendations.set(recommendation_id, recommendation);
      return json(200, recommendation);
    }
    if (method === 'POST' && parts[3] === 'override') {
      recommendation.status = 'OVERRIDDEN';
      db.recommendations.set(recommendation_id, recommendation);
      return json(200, recommendation);
    }
  }

  return json(404, { error: 'not_found' });
}
