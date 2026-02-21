import unittest

from app.schemas import Action, Classification
from app.scoring import SignalSummary, classify_and_action, compute_scores


class ScoringTests(unittest.TestCase):
    def test_underpowered(self) -> None:
        s = SignalSummary(
            gpu_util_p95=98,
            vram_used_p95_pct=99,
            cpu_util_p95=95,
            ram_used_p95=97,
            paging_pressure_minutes=200,
            disk_latency_p95_ms=100,
            disk_busy_minutes=400,
            disk_queue_p95=5,
            thermal_throttle_events=10,
            active_minutes=600,
            light_app_mix_factor=0.1,
        )
        c, a = classify_and_action(compute_scores(s))
        self.assertEqual(c, Classification.UNDERPOWERED)
        self.assertEqual(a, Action.UPSIZE)


if __name__ == "__main__":
    unittest.main()
