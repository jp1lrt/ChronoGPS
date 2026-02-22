# weak_sync_logic.py
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Deque, Literal, Optional, Sequence

Action = Literal["collecting", "skip", "strong_set", "pending", "set"]

@dataclass
class WeakSyncDecision:
    action: Action
    med: float
    sign: int
    confirm_count: int
    last_sign: int

def decide_weak_sync(
    diffs: Sequence[float],
    threshold: float,
    strong_threshold: float,
    confirm_needed: int,
    last_sign: int,
    confirm_count: int,
) -> WeakSyncDecision:
    """
    Pure decision logic for weak sync.
    - diffs: collected diff samples (adjusted_time - system_time)
    - threshold: deadband threshold
    - strong_threshold: force set threshold
    - confirm_needed: consecutive same-direction requirement
    - last_sign/confirm_count: carry-over state

    Returns decision and the next state values.
    """
    if len(diffs) == 0:
        return WeakSyncDecision("collecting", 0.0, 0, confirm_count=0, last_sign=0)

    med = float(median(diffs))

    # deadband
    if abs(med) < float(threshold):
        return WeakSyncDecision("skip", med, 0, confirm_count=0, last_sign=0)

    # strong: immediate
    if abs(med) >= float(strong_threshold):
        return WeakSyncDecision("strong_set", med, 0, confirm_count=0, last_sign=0)

    # confirm-stability
    sign = 1 if med > 0 else -1
    if sign == int(last_sign):
        confirm_count = int(confirm_count) + 1
    else:
        last_sign = sign
        confirm_count = 1

    if confirm_count < int(confirm_needed):
        return WeakSyncDecision("pending", med, sign, confirm_count=confirm_count, last_sign=last_sign)

    # confirmed: apply set
    return WeakSyncDecision("set", med, sign, confirm_count=0, last_sign=0)