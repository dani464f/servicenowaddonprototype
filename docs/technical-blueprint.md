# ServiceNow ITAM Add-on Technical Blueprint (Windows-first MVP + Scalable v1)

## Scope assumptions resolved from stakeholder feedback
- **Tenant model**: multi-tenant from day one with strict tenant isolation.
- **Telemetry source (MVP)**: choose a **custom Windows collector** for deterministic field coverage (GPU/VRAM/thermal/session context) and privacy controls.
- **ServiceNow integration approach (MVP)**: **Import Set API + Transform Maps** as default; Table API for low-volume control records.
- **Action policy**: recommendation actions may **auto-execute** when confidence and policy gates pass.
- **Privacy mode**: strict mode is configurable **per policy**.
- **Security baseline**: OAuth2 + mTLS, envelope encryption, full audit trail.
- **Workflow scope**: include reallocation, upgrade, exception, and refresh workflows in MVP.
- **Learning strategy**: unsupervised-first in MVP, supervised in v1 once outcomes accrue.

---

## A) High-level architecture and data flow
1. **Windows Endpoint Collector** (service + scheduled sampler)
   - Collects CPU/RAM/disk/network/GPU/thermal/session/app category signals every 5 minutes.
   - Performs local privacy filtering (default mode vs strict mode).
2. **Ingestion API**
   - Validates schema version + tenant identity + device signature.
   - Emits telemetry batches to stream queue and persists immutable raw payload.
3. **Stream/Queue Layer (Kafka)**
   - Topics: `telemetry.raw`, `capability.snapshots`, `policy.events`, `recommendation.events`.
4. **Raw Store (object storage)**
   - Partitioned by `tenant_id/date/source_type/device_id_hash`.
5. **Normalization + Aggregation Jobs (Spark/Flink scheduled)**
   - Canonical mapping from source fields to internal metric schema.
   - Produces daily endpoint summary and rolling windows (30/60/90 days).
6. **Feature Store (PostgreSQL + parquet features)**
   - Stores workload fingerprints and derived scores for rules + ML.
7. **Recommendation Engine**
   - Day-1 rules engine computes fit/overprovision and actions.
   - Optional ML layer adjusts confidence and identifies cohort anomalies.
8. **ServiceNow Integration Worker**
   - Pushes summaries and recommendations to Import Set staging tables, then transform into CMDB/ITAM and custom `u_*` tables.
9. **Web App + API (Admin/Analyst)**
   - Policy management, explainability, overrides, approvals, and audit.
10. **Observability + Audit**
   - Metrics, logs, traces, policy change history, recommendation decision records.

Data flow: `Collector -> Ingestion API -> Kafka -> Raw Store + Normalizer -> Aggregates/Features -> Recommendation Engine -> ServiceNow + Web UI`.

## B) Canonical data model (multi-tenant)

### Core relational tables (PostgreSQL)
1. `tenant`
   - `tenant_id (uuid pk)`, `name`, `region`, `status`, `created_at`.
   - Index: `unique(name)`.
2. `device_identity`
   - `device_id (uuid pk)`, `tenant_id`, `source_device_key`, `serial_number`, `bios_uuid`, `aad_device_id`, `last_seen_at`.
   - Indexes: `(tenant_id, source_device_key unique)`, `(tenant_id, serial_number)`.
3. `capability_snapshot`
   - `snapshot_id`, `tenant_id`, `device_id`, `captured_at`, `cpu_model`, `cpu_cores`, `ram_gb`, `disk_type`, `disk_total_gb`, `gpu_vendor`, `gpu_model`, `gpu_vram_gb`, `driver_version`, `tier_assigned`.
   - Indexes: `(tenant_id, device_id, captured_at desc)`, `(tenant_id, tier_assigned)`.
4. `telemetry_daily_summary`
   - `summary_id`, `tenant_id`, `device_id`, `summary_date`, `gpu_util_p95`, `vram_used_p95`, `gpu_active_minutes`, `cpu_util_p95`, `cpu_sustained_high_minutes`, `ram_used_p95`, `paging_pressure_minutes`, `disk_latency_p95_ms`, `disk_busy_minutes`, `disk_queue_p95`, `net_throughput_p95_mbps`, `net_loss_proxy_score`, `thermal_throttle_events`, `battery_percent_minutes`, `docking_frequency_score`, `vdi_indicator_rate`, `interactive_ratio`.
   - Indexes: `(tenant_id, summary_date)`, `(tenant_id, device_id, summary_date unique)`.
5. `workload_app_category_daily`
   - `id`, `tenant_id`, `device_id`, `summary_date`, `category`, `active_minutes`, `publisher_hash`, `process_name_hash`.
   - In strict mode, publisher/process hashes are null.
   - Indexes: `(tenant_id, device_id, summary_date)`, `(tenant_id, category, summary_date)`.
6. `recommendation`
   - `recommendation_id`, `tenant_id`, `device_id`, `run_date`, `classification`, `action`, `confidence`, `workload_fit_score`, `overprovision_score`, `expected_savings_usd_annual`, `risk_flags jsonb`, `top_reasons jsonb`, `status`, `executed_at`.
   - Indexes: `(tenant_id, run_date desc)`, `(tenant_id, action, status)`, `(tenant_id, device_id, run_date desc)`.
7. `policy_profile`
   - `policy_id`, `tenant_id`, `name`, `strict_mode`, `thresholds jsonb`, `auto_execute_rules jsonb`, `effective_from`, `effective_to`.
   - Indexes: `(tenant_id, effective_from desc)`.
8. `audit_event`
   - `event_id`, `tenant_id`, `actor_type`, `actor_id`, `event_type`, `resource_type`, `resource_id`, `before jsonb`, `after jsonb`, `created_at`.
   - Indexes: `(tenant_id, created_at desc)`, `(tenant_id, event_type)`.

### Multi-tenant isolation
- All rows include `tenant_id`; enforce PostgreSQL RLS policy `tenant_id = current_setting('app.tenant_id')`.
- Per-tenant encryption key alias for sensitive columns (envelope encryption).
- Kafka topics keyed by `tenant_id` for partition locality + quota controls.

## C) API contracts

### Versioning strategy
- URI versioning: `/api/v1/...`.
- Payload includes `schema_version` (`1.0`, `1.1` backward-compatible additions only).
- Reject unknown major versions with `422` + migration hint.

### Ingestion endpoints
1. `POST /api/v1/ingestion/telemetry-batch`
```json
{
  "schema_version": "1.0",
  "tenant_id": "8fd9a560-3e5b-4f84-8fd8-8f7f8ef67801",
  "source": "windows_collector",
  "batch_id": "b-2026-02-20-00017",
  "sent_at": "2026-02-20T02:10:00Z",
  "records": [
    {
      "device_key": "WIN-9f2a...",
      "observed_at": "2026-02-20T02:05:00Z",
      "session": {"vdi": false, "interactive_ratio": 0.82},
      "gpu": {"util_pct": 76, "vram_used_mb": 5300, "active_minutes": 5, "compute_pct": 20, "graphics_pct": 56},
      "cpu": {"util_pct": 68},
      "ram": {"used_pct": 79, "paging_pressure": 0},
      "disk": {"latency_ms": 23, "busy_pct": 67, "queue_len": 1.7},
      "network": {"throughput_mbps": 22.4, "loss_proxy": 0.01},
      "thermal": {"throttle_event": false, "on_battery": true, "docked": false},
      "apps": [
        {"publisher": "Autodesk", "process": "acad.exe", "category": "CAD", "active_minutes": 4},
        {"publisher": "Microsoft", "process": "chrome.exe", "category": "BROWSER_HEAVY", "active_minutes": 5}
      ]
    }
  ]
}
```
2. `POST /api/v1/ingestion/capability-snapshots`
```json
{
  "schema_version": "1.0",
  "tenant_id": "8fd9a560-3e5b-4f84-8fd8-8f7f8ef67801",
  "source": "windows_collector",
  "snapshots": [
    {
      "device_key": "WIN-9f2a...",
      "captured_at": "2026-02-20T01:00:00Z",
      "cpu": {"model": "Intel i7-12800H", "cores": 14},
      "ram_gb": 32,
      "storage": {"type": "NVMe", "total_gb": 1024},
      "gpu": {"vendor": "NVIDIA", "model": "RTX A2000", "vram_gb": 8, "driver": "552.22"}
    }
  ]
}
```

### Admin/policy endpoints
- `POST /api/v1/admin/policies`
- `GET /api/v1/admin/policies/{policy_id}`
- `PATCH /api/v1/admin/policies/{policy_id}`
- `POST /api/v1/admin/policies/{policy_id}/simulate`

### Recommendation endpoints
- `GET /api/v1/recommendations?tenant_id=&action=&classification=&min_confidence=&date_from=&date_to=`
- `GET /api/v1/recommendations/{recommendation_id}`
- `POST /api/v1/recommendations/{recommendation_id}/approve`
- `POST /api/v1/recommendations/{recommendation_id}/override`

## D) Pipeline design
- **Queue/stream**: Kafka (high throughput, replay support, partitioned by tenant).
- **Raw store**: S3/Blob immutable parquet + JSON envelope.
- **Aggregation jobs**:
  - Nearline micro-batch every 15 minutes to compute intraday counters.
  - Daily finalize job at tenant-local 02:00 for p95 metrics + category totals.
- **Feature store**:
  - PostgreSQL online features for UI/API.
  - Parquet offline feature snapshots for model training.
- **Recommendation run cadence**: daily post-finalize + on-demand simulate endpoint.

### Idempotency/dedupe
- Idempotency key: `(tenant_id, source, batch_id)` at ingestion.
- Record hash: SHA-256 of normalized `(device_key, observed_at, metric payload)`.
- Upsert daily summary on `(tenant_id, device_id, summary_date)`.

### Retention
- Raw telemetry: 30 days hot, 90 days cold archive.
- Daily summaries/features/recommendations: 24 months.
- Audit events/policy changes: 7 years (compliance-friendly).

## E) Scoring formulas (initial rules)

Let values be normalized to [0,1]. Tenant policy can override weights/thresholds.

1. **GPU Pressure Score**
- `gpu_pressure = 0.6*norm(gpu_util_p95, 40, 95) + 0.4*norm(vram_used_p95_pct, 50, 98)`
- High flag if `gpu_util_p95 >= 85` for `>= 10 days / 30`.

2. **RAM Pressure Score**
- `ram_pressure = 0.7*norm(ram_used_p95, 60, 98) + 0.3*norm(paging_pressure_minutes, 0, 180)`

3. **Disk Bottleneck Score**
- `disk_score = 0.5*norm(disk_latency_p95_ms, 10, 80) + 0.3*norm(disk_busy_minutes, 30, 360) + 0.2*norm(disk_queue_p95, 1, 5)`

4. **Overall Workload Fit Score (0-100, higher better fit)**
- `stress = 0.30*gpu_pressure + 0.25*ram_pressure + 0.20*disk_score + 0.20*cpu_pressure + 0.05*thermal_penalty`
- `fit = 100 - (stress*100)`

5. **Overprovision Score (0-100, higher means overprovisioned)**
- `overprov = 100 * (0.35*(1-gpu_pressure) + 0.25*(1-cpu_pressure) + 0.20*(1-ram_pressure) + 0.10*low_active_minutes_factor + 0.10*light_app_mix_factor)`

### Default classifications
- `UNDERPOWERED`: fit < 45 or any critical pressure > 0.90.
- `RIGHT_SIZED`: fit 45–75 and no critical flags.
- `OVERPROVISIONED`: fit > 75 and overprov > 65.

### Actions
- `DOWNSIZE` (overprov high, low risk), `UPSIZE` (underpowered high confidence), `REALLOCATE` (user-role mismatch), `EXTEND_LIFE` (right-sized + healthy), `REFRESH` (underpowered + aging), `INVESTIGATE` (conflicting or low-confidence signals).

### Tenant overrides
- Policy JSON supports per persona/department: thresholds, min sample days, auto-execute gates, excluded categories/devices.

## F) AI learning layer

### MVP (unsupervised)
- Build workload fingerprint vector per device-user window:
  - `[gpu_p95, vram_p95, cpu_p95, ram_p95, disk_lat_p95, active_minutes, app_category_distribution...]`.
- Use HDBSCAN/KMeans (tenant-specific) to discover workload cohorts.
- Compare assigned hardware tiers per cohort; detect outliers for upsizing/downsizing.
- Confidence = rules confidence * cluster stability factor * data completeness.

### v1 (supervised)
- Label from outcomes: ticket reopen, incident rate, user complaints, override rate, post-change telemetry improvement.
- Train gradient boosted model to predict best tier/action.
- Maintain champion/challenger with monthly retraining.

### Explainability + abstain
- Always return top 3 feature contributions (SHAP-like for supervised; distance-to-centroid for unsupervised).
- **Abstain** when data completeness < 70%, cluster confidence low, or policy conflict; fallback action = `INVESTIGATE`.

## G) ServiceNow implementation plan

### Standard tables to extend
1. `cmdb_ci_computer`
   - Add `u_workload_fit_score`, `u_overprov_score`, `u_capability_tier`, `u_last_telemetry_date`, `u_recommendation_state`.
2. `alm_hardware`
   - Add `u_rightsize_action`, `u_expected_savings`, `u_risk_flags`, `u_confidence_score`, `u_recommendation_date`.

### New custom tables
1. `u_hw_daily_summary`
   - FK to CI (`cmdb_ci_computer`), date, all p95 metrics, active minutes, app category rollups.
2. `u_hw_recommendation`
   - FK to CI + asset, classification/action/confidence/reasons/savings/status.
3. `u_hw_policy_snapshot`
   - policy version applied during recommendation run.
4. `u_hw_identity_map`
   - `tenant_id`, external `device_key`, `cmdb_ci.sys_id`, `alm_hardware.sys_id`, checksum, last_sync.

### sys_id mapping strategy
- Primary match order during sync:
  1) `u_hw_identity_map` hit by `(tenant_id, device_key)`.
  2) `serial_number` + `manufacturer` exact match.
  3) `asset_tag` fallback.
- Persist resolved links in `u_hw_identity_map` to avoid rematch drift.

### Integration approach
- Bulk telemetry/recommendations: Import Set API -> staging tables -> Transform Maps -> target tables.
- Control plane records (policy sync, acknowledgements): Table API.
- MID Server optional when ServiceNow instance cannot receive direct inbound traffic.

### Dashboards/list views
- ITAM analyst dashboard widgets:
  - Devices by classification.
  - Annualized savings by action.
  - Risk heatmap by business unit.
  - Underpowered devices with incident overlay.
- List views:
  - `u_hw_recommendation` grouped by action/status.
  - `u_hw_daily_summary` filtered by threshold breaches.

### Workflow outlines (Flow Designer)
1. **Reallocation**: recommendation -> approval (optional by policy) -> task to desktop ops -> completion telemetry check.
2. **Upgrade**: create procurement/change task -> fulfillment -> post-change validation after 14 days.
3. **Exception**: policy conflict or executive exemption -> security/ITAM review -> expiry-based revalidation.
4. **Refresh**: aging asset + underpowered signals -> refresh queue + budget tag.

## H) Frontend design (web app)

### Pages
- Overview dashboard.
- Device explorer (filters: tenant, BU, tier, action, confidence, privacy mode).
- Recommendation inbox (approve/override/bulk actions).
- Policy studio (thresholds, auto-exec gates, strict mode by policy scope).
- Governance/audit center (decision log, model run explainability, drift alerts).
- Connector health page (collector heartbeat, ingestion lag, ServiceNow sync status).

### Roles / RBAC
- `tenant_admin`: full policy + integration config.
- `itam_analyst`: review/approve/override recommendations.
- `privacy_officer`: strict-mode enforcement, data export approvals.
- `ops_executor`: execute assigned upgrade/reallocation tasks.
- `read_only_finance`: savings dashboards only.

### Key journeys
1. ITAM analyst triages `UNDERPOWERED` list -> approves `UPSIZE` batch -> tracks completion.
2. Admin tunes thresholds for CAD department -> runs simulation -> publishes policy.
3. Privacy officer audits strict-mode policy coverage and verifies no process-level detail leakage.

## I) Security and compliance
- **Auth**: OIDC/OAuth2 for users (Entra ID recommended), service-to-service OAuth2 client credentials + mTLS.
- **Encryption**: TLS 1.2+ in transit, AES-256 at rest, per-tenant DEK wrapped by KMS CMK.
- **RBAC/ABAC**: tenant-scoped roles, optional BU attribute constraints.
- **Audit**: immutable audit events for policy changes, recommendation overrides, data exports.
- **Privacy controls**:
  - Default mode: publisher/process allowed (no paths/titles/URLs/keystrokes).
  - Strict mode (per policy): only category-level app signals.
- **Data residency**: deploy per-region data plane; keep telemetry + raw storage region-pinned.

## J) Deployment plan (MVP 8–12 weeks)

### Suggested stack
- Backend APIs: TypeScript (NestJS) or Python (FastAPI); choose **FastAPI** for rapid schema validation + data workloads.
- Data jobs: PySpark.
- DB: PostgreSQL 15.
- Queue: Kafka (MSK/Confluent equivalent).
- Raw/object: S3-compatible storage.
- Frontend: React + TypeScript.
- Infra: Kubernetes + Helm + Terraform.

### Multi-tenant scaling
- Shared control plane, tenant-partitioned data plane tables.
- Horizontal scale on ingestion workers by Kafka lag.
- Partition `telemetry_daily_summary` by month + tenant hash.
- Target throughput: 100k endpoints, 5-min samples, <5 min ingestion lag, daily recommendations by 06:00 local.

### Observability/SLOs
- SLOs:
  - ingestion success >= 99.5%
  - recommendation job completion >= 99% by SLA window
  - ServiceNow sync success >= 99%
- Instrument with OpenTelemetry, Prometheus, Grafana, and alerting on lag/error budgets.

### MVP delivery sequencing (8–12 weeks)
1. Weeks 1–2: collector + ingestion + canonical schema.
2. Weeks 3–4: aggregation pipeline + daily summary tables + base UI pages.
3. Weeks 5–6: rules engine + recommendation APIs + explainability.
4. Weeks 7–8: ServiceNow import sets, transform maps, workflows.
5. Weeks 9–10: RBAC/privacy modes, hardening, UAT pilot.
6. Weeks 11–12: production rollout + tuning + v1 ML readiness backlog.
