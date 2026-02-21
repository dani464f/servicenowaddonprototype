from __future__ import annotations

from dataclasses import dataclass

from app.schemas import Action, Classification


def norm(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    if value <= floor:
        return 0.0
    if value >= ceiling:
        return 1.0
    return (value - floor) / (ceiling - floor)


@dataclass
class SignalSummary:
    gpu_util_p95: float
    vram_used_p95_pct: float
    cpu_util_p95: float
    ram_used_p95: float
    paging_pressure_minutes: float
    disk_latency_p95_ms: float
    disk_busy_minutes: float
    disk_queue_p95: float
    thermal_throttle_events: int
    active_minutes: float
    light_app_mix_factor: float


def compute_scores(s: SignalSummary) -> dict[str, float]:
    gpu_pressure = 0.6 * norm(s.gpu_util_p95, 40, 95) + 0.4 * norm(s.vram_used_p95_pct, 50, 98)
    cpu_pressure = norm(s.cpu_util_p95, 40, 95)
    ram_pressure = 0.7 * norm(s.ram_used_p95, 60, 98) + 0.3 * norm(s.paging_pressure_minutes, 0, 180)
    disk_score = (
        0.5 * norm(s.disk_latency_p95_ms, 10, 80)
        + 0.3 * norm(s.disk_busy_minutes, 30, 360)
        + 0.2 * norm(s.disk_queue_p95, 1, 5)
    )
    thermal_penalty = norm(float(s.thermal_throttle_events), 0, 15)
    stress = 0.30 * gpu_pressure + 0.25 * ram_pressure + 0.20 * disk_score + 0.20 * cpu_pressure + 0.05 * thermal_penalty
    fit = max(0.0, min(100.0, 100 - (stress * 100)))

    low_active_minutes_factor = 1.0 - norm(s.active_minutes, 60, 480)
    overprov = 100 * (
        0.35 * (1 - gpu_pressure)
        + 0.25 * (1 - cpu_pressure)
        + 0.20 * (1 - ram_pressure)
        + 0.10 * low_active_minutes_factor
        + 0.10 * s.light_app_mix_factor
    )
    return {
        "gpu_pressure": gpu_pressure,
        "cpu_pressure": cpu_pressure,
        "ram_pressure": ram_pressure,
        "disk_score": disk_score,
        "fit": fit,
        "overprov": max(0.0, min(100.0, overprov)),
    }


def classify_and_action(scores: dict[str, float]) -> tuple[Classification, Action]:
    critical = max(scores["gpu_pressure"], scores["cpu_pressure"], scores["ram_pressure"], scores["disk_score"])
    if scores["fit"] < 45 or critical > 0.90:
        return Classification.UNDERPOWERED, Action.UPSIZE
    if scores["fit"] > 75 and scores["overprov"] > 65:
        return Classification.OVERPROVISIONED, Action.DOWNSIZE
    return Classification.RIGHT_SIZED, Action.EXTEND_LIFE
