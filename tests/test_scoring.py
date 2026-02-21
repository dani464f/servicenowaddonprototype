from app.scoring import SignalSummary, classify_and_action, compute_scores
from app.schemas import Action, Classification


def test_underpowered_classification() -> None:
    s = SignalSummary(
        gpu_util_p95=95,
        vram_used_p95_pct=99,
        cpu_util_p95=92,
        ram_used_p95=97,
        paging_pressure_minutes=240,
        disk_latency_p95_ms=120,
        disk_busy_minutes=420,
        disk_queue_p95=7,
        thermal_throttle_events=8,
        active_minutes=600,
        light_app_mix_factor=0.1,
    )
    scores = compute_scores(s)
    classification, action = classify_and_action(scores)
    assert classification == Classification.UNDERPOWERED
    assert action == Action.UPSIZE


def test_overprovisioned_classification() -> None:
    s = SignalSummary(
        gpu_util_p95=15,
        vram_used_p95_pct=10,
        cpu_util_p95=20,
        ram_used_p95=35,
        paging_pressure_minutes=0,
        disk_latency_p95_ms=3,
        disk_busy_minutes=10,
        disk_queue_p95=0.3,
        thermal_throttle_events=0,
        active_minutes=35,
        light_app_mix_factor=1.0,
    )
    scores = compute_scores(s)
    classification, action = classify_and_action(scores)
    assert classification == Classification.OVERPROVISIONED
    assert action == Action.DOWNSIZE
