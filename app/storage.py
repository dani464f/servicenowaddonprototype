from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from uuid import uuid4

from app.schemas import (
    Action,
    CapabilityBatchIn,
    Classification,
    PolicyCreateIn,
    PolicyPatchIn,
    PolicyProfile,
    Recommendation,
    TelemetryBatchIn,
)
from app.scoring import SignalSummary, classify_and_action, compute_scores


class InMemoryStore:
    def __init__(self) -> None:
        self.ingested_batches: set[tuple[str, str, str]] = set()
        self.telemetry: dict[str, list[TelemetryBatchIn]] = defaultdict(list)
        self.capabilities: dict[str, list[CapabilityBatchIn]] = defaultdict(list)
        self.policies: dict[str, PolicyProfile] = {}
        self.recommendations: dict[str, Recommendation] = {}

    def ingest_telemetry(self, payload: TelemetryBatchIn) -> tuple[int, bool]:
        key = (payload.tenant_id, payload.source, payload.batch_id)
        if key in self.ingested_batches:
            return 0, True
        self.ingested_batches.add(key)
        self.telemetry[payload.tenant_id].append(payload)
        return len(payload.records), False

    def ingest_capabilities(self, payload: CapabilityBatchIn) -> int:
        self.capabilities[payload.tenant_id].append(payload)
        return len(payload.snapshots)

    def create_policy(self, payload: PolicyCreateIn) -> PolicyProfile:
        policy = PolicyProfile(
            policy_id=str(uuid4()),
            tenant_id=payload.tenant_id,
            name=payload.name,
            strict_mode=payload.strict_mode,
            thresholds=payload.thresholds,
            auto_execute_rules=payload.auto_execute_rules,
            effective_from=datetime.now(UTC),
            effective_to=None,
        )
        self.policies[policy.policy_id] = policy
        return policy

    def get_policy(self, policy_id: str) -> PolicyProfile | None:
        return self.policies.get(policy_id)

    def patch_policy(self, policy_id: str, patch: PolicyPatchIn) -> PolicyProfile | None:
        policy = self.policies.get(policy_id)
        if not policy:
            return None
        data = policy.model_dump()
        for field, value in patch.model_dump(exclude_none=True).items():
            data[field] = value
        updated = PolicyProfile(**data)
        self.policies[policy_id] = updated
        return updated

    def generate_recommendations(self, tenant_id: str) -> list[Recommendation]:
        batches = self.telemetry.get(tenant_id, [])
        if not batches:
            return []

        by_device: dict[str, list] = defaultdict(list)
        for batch in batches:
            by_device.update({})
            for r in batch.records:
                by_device[r.device_key].append(r)

        results: list[Recommendation] = []
        for device_key, recs in by_device.items():
            gpu_util_p95 = sorted([x.gpu.util_pct for x in recs])[int(0.95 * (len(recs) - 1))]
            cpu_util_p95 = sorted([x.cpu.util_pct for x in recs])[int(0.95 * (len(recs) - 1))]
            ram_used_p95 = sorted([x.ram.used_pct for x in recs])[int(0.95 * (len(recs) - 1))]
            vram_pct_values = [min(100.0, x.gpu.vram_used_mb / 8192.0 * 100.0) for x in recs]
            vram_used_p95_pct = sorted(vram_pct_values)[int(0.95 * (len(vram_pct_values) - 1))]
            paging_minutes = sum(x.ram.paging_pressure for x in recs)
            disk_latency_p95_ms = sorted([x.disk.latency_ms for x in recs])[int(0.95 * (len(recs) - 1))]
            disk_busy_minutes = sum((x.disk.busy_pct / 100.0) * 5 for x in recs)
            disk_queue_p95 = sorted([x.disk.queue_len for x in recs])[int(0.95 * (len(recs) - 1))]
            thermal_events = sum(1 for x in recs if x.thermal.throttle_event)
            active_minutes = sum(x.gpu.active_minutes for x in recs)
            heavy_categories = {"CAD", "ML", "VIDEO", "IDE", "BI"}
            total_app_minutes = sum(a.active_minutes for x in recs for a in x.apps) or 1
            heavy_minutes = sum(
                a.active_minutes for x in recs for a in x.apps if a.category.upper() in heavy_categories
            )
            light_app_mix_factor = max(0.0, min(1.0, 1 - heavy_minutes / total_app_minutes))

            signals = SignalSummary(
                gpu_util_p95=gpu_util_p95,
                vram_used_p95_pct=vram_used_p95_pct,
                cpu_util_p95=cpu_util_p95,
                ram_used_p95=ram_used_p95,
                paging_pressure_minutes=paging_minutes,
                disk_latency_p95_ms=disk_latency_p95_ms,
                disk_busy_minutes=disk_busy_minutes,
                disk_queue_p95=disk_queue_p95,
                thermal_throttle_events=thermal_events,
                active_minutes=active_minutes,
                light_app_mix_factor=light_app_mix_factor,
            )
            scores = compute_scores(signals)
            classification, action = classify_and_action(scores)
            confidence = 0.85
            if classification == Classification.RIGHT_SIZED:
                confidence = 0.70
            if action == Action.DOWNSIZE and scores["overprov"] > 80:
                confidence = 0.90

            rec = Recommendation(
                recommendation_id=str(uuid4()),
                tenant_id=tenant_id,
                device_key=device_key,
                run_date=date.today(),
                classification=classification,
                action=action,
                confidence=confidence,
                workload_fit_score=round(scores["fit"], 2),
                overprovision_score=round(scores["overprov"], 2),
                expected_savings_usd_annual=1200.0 if action == Action.DOWNSIZE else 0.0,
                risk_flags=["THERMAL"] if thermal_events > 3 else [],
                top_reasons=[
                    f"GPU pressure={scores['gpu_pressure']:.2f}",
                    f"RAM pressure={scores['ram_pressure']:.2f}",
                    f"Disk score={scores['disk_score']:.2f}",
                ],
                status="PENDING" if action != Action.EXTEND_LIFE else "NO_ACTION",
            )
            self.recommendations[rec.recommendation_id] = rec
            results.append(rec)
        return results


store = InMemoryStore()
