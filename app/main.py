from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from app.schemas import (
    CapabilityBatchIn,
    IngestionAck,
    PolicyCreateIn,
    PolicyPatchIn,
    PolicyProfile,
    Recommendation,
    RecommendationListOut,
    SimulateRequest,
    TelemetryBatchIn,
)
from app.storage import store

app = FastAPI(title="ServiceNow ITAM Add-on API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ingestion/telemetry-batch", response_model=IngestionAck)
def ingest_telemetry(payload: TelemetryBatchIn) -> IngestionAck:
    accepted, deduped = store.ingest_telemetry(payload)
    return IngestionAck(
        status="accepted" if not deduped else "duplicate",
        tenant_id=payload.tenant_id,
        accepted_records=accepted,
        deduped=deduped,
    )


@app.post("/api/v1/ingestion/capability-snapshots", response_model=IngestionAck)
def ingest_capabilities(payload: CapabilityBatchIn) -> IngestionAck:
    accepted = store.ingest_capabilities(payload)
    return IngestionAck(status="accepted", tenant_id=payload.tenant_id, accepted_records=accepted)


@app.post("/api/v1/admin/policies", response_model=PolicyProfile)
def create_policy(payload: PolicyCreateIn) -> PolicyProfile:
    return store.create_policy(payload)


@app.get("/api/v1/admin/policies/{policy_id}", response_model=PolicyProfile)
def get_policy(policy_id: str) -> PolicyProfile:
    policy = store.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="policy_not_found")
    return policy


@app.patch("/api/v1/admin/policies/{policy_id}", response_model=PolicyProfile)
def patch_policy(policy_id: str, patch: PolicyPatchIn) -> PolicyProfile:
    updated = store.patch_policy(policy_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="policy_not_found")
    return updated


@app.post("/api/v1/admin/policies/{policy_id}/simulate", response_model=RecommendationListOut)
def simulate_policy(policy_id: str, payload: SimulateRequest) -> RecommendationListOut:
    policy = store.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="policy_not_found")
    return RecommendationListOut(items=store.generate_recommendations(payload.tenant_id))


@app.get("/api/v1/recommendations", response_model=RecommendationListOut)
def list_recommendations(
    tenant_id: str,
    action: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None),
) -> RecommendationListOut:
    recs = [x for x in store.recommendations.values() if x.tenant_id == tenant_id]
    if action:
        recs = [x for x in recs if x.action == action]
    if classification:
        recs = [x for x in recs if x.classification == classification]
    if min_confidence is not None:
        recs = [x for x in recs if x.confidence >= min_confidence]
    return RecommendationListOut(items=recs)


@app.get("/api/v1/recommendations/{recommendation_id}", response_model=Recommendation)
def get_recommendation(recommendation_id: str) -> Recommendation:
    rec = store.recommendations.get(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    return rec


@app.post("/api/v1/recommendations/{recommendation_id}/approve", response_model=Recommendation)
def approve_recommendation(recommendation_id: str) -> Recommendation:
    rec = store.recommendations.get(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    rec.status = "APPROVED"
    store.recommendations[recommendation_id] = rec
    return rec


@app.post("/api/v1/recommendations/{recommendation_id}/override", response_model=Recommendation)
def override_recommendation(recommendation_id: str) -> Recommendation:
    rec = store.recommendations.get(recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    rec.status = "OVERRIDDEN"
    store.recommendations[recommendation_id] = rec
    return rec
