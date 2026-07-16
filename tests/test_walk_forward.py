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


def test_verdict_low_sample_uses_absolute_floor():
    # In-sample PF of 12.71 from only 6 trades is noise: the ratio floor (7.6)
    # must NOT apply. OOS segments merely need to be profitable (PF >= 1.0).
    verdict = wf.evaluate_segments(in_sample_pf=12.71, oos_pfs=[2.29, 2.28],
                                   in_sample_trades=6)
    assert verdict["low_sample"] is True
    assert verdict["floor"] == 1.0
    assert verdict["passed"] is True


def test_verdict_low_sample_still_fails_unprofitable_oos():
    verdict = wf.evaluate_segments(in_sample_pf=999.0, oos_pfs=[1.5, 0.8],
                                   in_sample_trades=3)
    assert verdict["passed"] is False
    assert verdict["failed_segments"] == [1]


def test_verdict_ratio_test_applies_with_enough_in_sample_trades():
    verdict = wf.evaluate_segments(in_sample_pf=2.0, oos_pfs=[1.8, 0.9],
                                   in_sample_trades=50)
    assert verdict["low_sample"] is False
    assert verdict["passed"] is False       # 0.9 < floor 1.2, ratio rule intact


def test_split_indices_are_non_overlapping():
    # 300 rows, 3 segments -> [(0,100),(100,200),(200,300)] contiguous, no overlap.
    segs = wf.split_indices(total=300, n_segments=3)
    assert segs == [(0, 100), (100, 200), (200, 300)]
    for (a_start, a_end), (b_start, b_end) in zip(segs, segs[1:]):
        assert a_end == b_start
