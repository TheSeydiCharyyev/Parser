from __future__ import annotations


def clamp_rps(rps: int) -> int:
    try:
        rps_int = int(rps)
    except Exception:
        rps_int = 1
    return max(1, min(rps_int, 10))


def refill_tokens(tokens: float, last_ts: float, now: float, rps: int, burst_seconds: float = 1.0) -> tuple[float, float]:
    """Token bucket refill.

    - tokens increase by dt * rps
    - cap burst to (rps * burst_seconds)
    """

    rps_v = float(clamp_rps(rps))
    if last_ts <= 0:
        last_ts = now

    dt = max(0.0, float(now) - float(last_ts))
    burst_cap = rps_v * float(burst_seconds)
    new_tokens = min(burst_cap, float(tokens) + dt * rps_v)
    return new_tokens, float(now)


def next_due_ts(tokens: float, rps: int, now: float) -> float:
    rps_v = float(clamp_rps(rps))
    if float(tokens) >= 1.0:
        return float(now)
    need = 1.0 - float(tokens)
    return float(now) + (need / rps_v)
