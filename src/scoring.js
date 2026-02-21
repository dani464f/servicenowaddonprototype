export function norm(value, floor, ceiling) {
  if (ceiling <= floor) return 0;
  if (value <= floor) return 0;
  if (value >= ceiling) return 1;
  return (value - floor) / (ceiling - floor);
}

export function computeScores(s) {
  const gpu_pressure = 0.6 * norm(s.gpu_util_p95, 40, 95) + 0.4 * norm(s.vram_used_p95_pct, 50, 98);
  const cpu_pressure = norm(s.cpu_util_p95, 40, 95);
  const ram_pressure = 0.7 * norm(s.ram_used_p95, 60, 98) + 0.3 * norm(s.paging_pressure_minutes, 0, 180);
  const disk_score = 0.5 * norm(s.disk_latency_p95_ms, 10, 80) + 0.3 * norm(s.disk_busy_minutes, 30, 360) + 0.2 * norm(s.disk_queue_p95, 1, 5);
  const thermal_penalty = norm(s.thermal_throttle_events || 0, 0, 15);
  const stress = 0.3 * gpu_pressure + 0.25 * ram_pressure + 0.2 * disk_score + 0.2 * cpu_pressure + 0.05 * thermal_penalty;
  const fit = Math.max(0, Math.min(100, 100 - stress * 100));

  const low_active_minutes_factor = 1 - norm(s.active_minutes, 60, 480);
  const overprov = 100 * (
    0.35 * (1 - gpu_pressure) +
    0.25 * (1 - cpu_pressure) +
    0.2 * (1 - ram_pressure) +
    0.1 * low_active_minutes_factor +
    0.1 * s.light_app_mix_factor
  );

  return { gpu_pressure, cpu_pressure, ram_pressure, disk_score, fit, overprov: Math.max(0, Math.min(100, overprov)) };
}

export function classifyAndAction(scores) {
  const critical = Math.max(scores.gpu_pressure, scores.cpu_pressure, scores.ram_pressure, scores.disk_score);
  if (scores.fit < 45 || critical > 0.9) {
    return { classification: 'UNDERPOWERED', action: 'UPSIZE' };
  }
  if (scores.fit > 75 && scores.overprov > 65) {
    return { classification: 'OVERPROVISIONED', action: 'DOWNSIZE' };
  }
  return { classification: 'RIGHT_SIZED', action: 'EXTEND_LIFE' };
}
