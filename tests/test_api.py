from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingestion_idempotency_and_recommendations_flow() -> None:
    telemetry_payload = {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "source": "windows_collector",
        "batch_id": "batch-1",
        "sent_at": "2026-02-20T02:10:00Z",
        "records": [
            {
                "device_key": "WIN-123",
                "observed_at": "2026-02-20T02:05:00Z",
                "session": {"vdi": False, "interactive_ratio": 0.8},
                "gpu": {"util_pct": 10, "vram_used_mb": 400, "active_minutes": 2, "compute_pct": 1, "graphics_pct": 9},
                "cpu": {"util_pct": 22},
                "ram": {"used_pct": 35, "paging_pressure": 0},
                "disk": {"latency_ms": 2, "busy_pct": 8, "queue_len": 0.2},
                "network": {"throughput_mbps": 5.0, "loss_proxy": 0.0},
                "thermal": {"throttle_event": False, "on_battery": True, "docked": False},
                "apps": [{"publisher": "Microsoft", "process": "outlook.exe", "category": "BROWSER_HEAVY", "active_minutes": 3}],
            }
        ],
    }

    first = client.post("/api/v1/ingestion/telemetry-batch", json=telemetry_payload)
    assert first.status_code == 200
    assert first.json()["accepted_records"] == 1
    assert first.json()["deduped"] is False

    second = client.post("/api/v1/ingestion/telemetry-batch", json=telemetry_payload)
    assert second.status_code == 200
    assert second.json()["accepted_records"] == 0
    assert second.json()["deduped"] is True

    policy_resp = client.post(
        "/api/v1/admin/policies",
        json={
            "tenant_id": "tenant-a",
            "name": "default",
            "strict_mode": True,
            "thresholds": {"gpu_util_high": 85},
            "auto_execute_rules": {"DOWNSIZE": {"min_confidence": 0.9}},
        },
    )
    assert policy_resp.status_code == 200
    policy_id = policy_resp.json()["policy_id"]

    sim = client.post(f"/api/v1/admin/policies/{policy_id}/simulate", json={"tenant_id": "tenant-a"})
    assert sim.status_code == 200
    assert len(sim.json()["items"]) >= 1

    recommendation_id = sim.json()["items"][0]["recommendation_id"]
    approve = client.post(f"/api/v1/recommendations/{recommendation_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"
