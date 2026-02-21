from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Classification(str, Enum):
    OVERPROVISIONED = "OVERPROVISIONED"
    RIGHT_SIZED = "RIGHT_SIZED"
    UNDERPOWERED = "UNDERPOWERED"


class Action(str, Enum):
    DOWNSIZE = "DOWNSIZE"
    UPSIZE = "UPSIZE"
    REALLOCATE = "REALLOCATE"
    EXTEND_LIFE = "EXTEND_LIFE"
    REFRESH = "REFRESH"
    INVESTIGATE = "INVESTIGATE"


class AppRecord(BaseModel):
    publisher: str | None = None
    process: str | None = None
    category: str
    active_minutes: int = Field(ge=0)


class SessionRecord(BaseModel):
    vdi: bool = False
    interactive_ratio: float = Field(ge=0.0, le=1.0)


class GPURecord(BaseModel):
    util_pct: float = Field(ge=0, le=100)
    vram_used_mb: float = Field(ge=0)
    active_minutes: int = Field(ge=0)
    compute_pct: float | None = Field(default=None, ge=0, le=100)
    graphics_pct: float | None = Field(default=None, ge=0, le=100)


class CPURecord(BaseModel):
    util_pct: float = Field(ge=0, le=100)


class RAMRecord(BaseModel):
    used_pct: float = Field(ge=0, le=100)
    paging_pressure: int = Field(ge=0)


class DiskRecord(BaseModel):
    latency_ms: float = Field(ge=0)
    busy_pct: float = Field(ge=0, le=100)
    queue_len: float = Field(ge=0)


class NetworkRecord(BaseModel):
    throughput_mbps: float = Field(ge=0)
    loss_proxy: float = Field(ge=0)


class ThermalRecord(BaseModel):
    throttle_event: bool = False
    on_battery: bool = False
    docked: bool = True


class TelemetryRecord(BaseModel):
    device_key: str
    observed_at: datetime
    session: SessionRecord
    gpu: GPURecord
    cpu: CPURecord
    ram: RAMRecord
    disk: DiskRecord
    network: NetworkRecord
    thermal: ThermalRecord
    apps: list[AppRecord] = Field(default_factory=list)


class TelemetryBatchIn(BaseModel):
    schema_version: str = "1.0"
    tenant_id: str
    source: str
    batch_id: str
    sent_at: datetime
    records: list[TelemetryRecord]


class CapabilityCPU(BaseModel):
    model: str
    cores: int = Field(gt=0)


class CapabilityStorage(BaseModel):
    type: str
    total_gb: int = Field(gt=0)


class CapabilityGPU(BaseModel):
    vendor: str
    model: str
    vram_gb: int = Field(ge=0)
    driver: str


class CapabilitySnapshot(BaseModel):
    device_key: str
    captured_at: datetime
    cpu: CapabilityCPU
    ram_gb: int = Field(gt=0)
    storage: CapabilityStorage
    gpu: CapabilityGPU


class CapabilityBatchIn(BaseModel):
    schema_version: str = "1.0"
    tenant_id: str
    source: str
    snapshots: list[CapabilitySnapshot]


class PolicyProfile(BaseModel):
    policy_id: str
    tenant_id: str
    name: str
    strict_mode: bool = False
    thresholds: dict[str, Any] = Field(default_factory=dict)
    auto_execute_rules: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime
    effective_to: datetime | None = None


class PolicyCreateIn(BaseModel):
    tenant_id: str
    name: str
    strict_mode: bool = False
    thresholds: dict[str, Any] = Field(default_factory=dict)
    auto_execute_rules: dict[str, Any] = Field(default_factory=dict)


class PolicyPatchIn(BaseModel):
    name: str | None = None
    strict_mode: bool | None = None
    thresholds: dict[str, Any] | None = None
    auto_execute_rules: dict[str, Any] | None = None


class Recommendation(BaseModel):
    recommendation_id: str
    tenant_id: str
    device_key: str
    run_date: date
    classification: Classification
    action: Action
    confidence: float = Field(ge=0, le=1)
    workload_fit_score: float = Field(ge=0, le=100)
    overprovision_score: float = Field(ge=0, le=100)
    expected_savings_usd_annual: float
    risk_flags: list[str]
    top_reasons: list[str]
    status: str


class RecommendationListOut(BaseModel):
    items: list[Recommendation]


class SimulateRequest(BaseModel):
    tenant_id: str


class IngestionAck(BaseModel):
    status: str
    tenant_id: str
    accepted_records: int
    deduped: bool = False
