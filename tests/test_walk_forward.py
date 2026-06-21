"""Tests for the strict walk-forward verdict logic."""
from __future__ import annotations

from backtest import walk_forward as wf


def test_verdict_passes_when_oos_holds():
    # in-sample PF 2.0, OOS PFs 1.8 and 1.6; ratio floor 0.6 -> need >= 1.2. Both pass.
    verdict = wf.evaluate_segments(in_sample_pf=2.0, oos_pfs=[1.8, 1.6], min_ratio=0.6)
    assert verdict["passed"] is True


def test_verdict_fails_on_oos_degradation():
    # OOS PF 0.9 < 1.2 floor -> fail.
    verdict = wf.evaluate_segments(in_sample_pf=2.0, oos_pfs=[1.8, 0.9], min_ratio=0.6)
    assert verdict["passed"] is False
    assert 1 in verdict["failed_segments"]   # second OOS segment (index 1) failed


def test_split_indices_are_non_overlapping():
    # 300 rows, 3 segments -> [(0,100),(100,200),(200,300)] contiguous, no overlap.
    segs = wf.split_indices(total=300, n_segments=3)
    assert segs == [(0, 100), (100, 200), (200, 300)]
    for (a_start, a_end), (b_start, b_end) in zip(segs, segs[1:]):
        assert a_end == b_start
