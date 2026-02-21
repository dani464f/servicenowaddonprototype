import test from 'node:test';
import assert from 'node:assert/strict';
import { handler } from '../netlify/functions/api.js';

function event(path, method, body, queryStringParameters = null) {
  return { path, httpMethod: method, body: body ? JSON.stringify(body) : null, queryStringParameters };
}

test('ingest -> policy -> simulate -> approve flow', async () => {
  const telemetry = {
    tenant_id: 'tenant-a',
    source: 'windows_collector',
    batch_id: 'batch-1',
    records: [{
      device_key: 'WIN-123',
      gpu: { util_pct: 10, vram_used_mb: 350, active_minutes: 2 },
      cpu: { util_pct: 20 },
      ram: { used_pct: 35, paging_pressure: 0 },
      disk: { latency_ms: 2, busy_pct: 8, queue_len: 0.2 },
      thermal: { throttle_event: false },
      apps: [{ category: 'BROWSER_HEAVY', active_minutes: 3 }]
    }]
  };

  const ingest1 = await handler(event('/.netlify/functions/api/v1/ingestion/telemetry-batch', 'POST', telemetry));
  assert.equal(ingest1.statusCode, 200);
  const ingestBody1 = JSON.parse(ingest1.body);
  assert.equal(ingestBody1.accepted_records, 1);

  const ingest2 = await handler(event('/.netlify/functions/api/v1/ingestion/telemetry-batch', 'POST', telemetry));
  const ingestBody2 = JSON.parse(ingest2.body);
  assert.equal(ingestBody2.deduped, true);

  const policy = await handler(event('/.netlify/functions/api/v1/admin/policies', 'POST', { tenant_id: 'tenant-a', name: 'default' }));
  const policyBody = JSON.parse(policy.body);
  assert.ok(policyBody.policy_id);

  const sim = await handler(event(`/.netlify/functions/api/v1/admin/policies/${policyBody.policy_id}/simulate`, 'POST', { tenant_id: 'tenant-a' }));
  const simBody = JSON.parse(sim.body);
  assert.ok(simBody.items.length >= 1);

  const recId = simBody.items[0].recommendation_id;
  const approve = await handler(event(`/.netlify/functions/api/v1/recommendations/${recId}/approve`, 'POST', {}));
  const approveBody = JSON.parse(approve.body);
  assert.equal(approveBody.status, 'APPROVED');
});
