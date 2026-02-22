# test_weak_sync_logic.py
from weak_sync_logic import decide_weak_sync

def test_decide_skip_within_threshold():
    d = decide_weak_sync(
        diffs=[0.02, -0.01, 0.03],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=0,
        confirm_count=0,
    )
    assert d.action == "skip"
    assert d.confirm_count == 0
    assert d.last_sign == 0

def test_decide_strong_set_over_strong_threshold():
    d = decide_weak_sync(
        diffs=[1.2, 1.1, 1.3],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=0,
        confirm_count=0,
    )
    assert d.action == "strong_set"
    assert d.confirm_count == 0
    assert d.last_sign == 0

def test_decide_pending_then_set_after_confirm_needed():
    # 1回目：新しい方向なので pending、count=1
    d1 = decide_weak_sync(
        diffs=[0.20, 0.18, 0.22],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=0,
        confirm_count=0,
    )
    assert d1.action == "pending"
    assert d1.last_sign == 1
    assert d1.confirm_count == 1

    # 2回目：同方向なので pending、count=2
    d2 = decide_weak_sync(
        diffs=[0.21, 0.19, 0.20],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=d1.last_sign,
        confirm_count=d1.confirm_count,
    )
    assert d2.action == "pending"
    assert d2.last_sign == 1
    assert d2.confirm_count == 2

    # 3回目：同方向で必要回数到達 → set
    d3 = decide_weak_sync(
        diffs=[0.22, 0.21, 0.20],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=d2.last_sign,
        confirm_count=d2.confirm_count,
    )
    assert d3.action == "set"
    assert d3.confirm_count == 0
    assert d3.last_sign == 0

def test_decide_resets_on_sign_flip():
    # まず +方向で1回目
    d1 = decide_weak_sync(
        diffs=[0.2, 0.2, 0.2],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=0,
        confirm_count=0,
    )
    assert d1.action == "pending"
    assert d1.last_sign == 1
    assert d1.confirm_count == 1

    # 次に -方向へ反転 → countは1にリセット、last_sign=-1
    d2 = decide_weak_sync(
        diffs=[-0.2, -0.2, -0.2],
        threshold=0.05,
        strong_threshold=1.0,
        confirm_needed=3,
        last_sign=d1.last_sign,
        confirm_count=d1.confirm_count,
    )
    assert d2.action == "pending"
    assert d2.last_sign == -1
    assert d2.confirm_count == 1