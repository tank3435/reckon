import pytest
from reckon.analysis.scorer import _zscore_to_100, _severity


def test_zscore_at_mean():
    # At the mean, score should be exactly 50
    assert _zscore_to_100(10.0, 10.0, 2.0, 3.0) == 50.0


def test_zscore_above_mean():
    # 3 stddevs above → clamped at top → score = 100
    assert _zscore_to_100(16.0, 10.0, 2.0, 3.0) == 100.0


def test_zscore_below_mean():
    # 3 stddevs below → clamped at bottom → score = 0
    assert _zscore_to_100(4.0, 10.0, 2.0, 3.0) == 0.0


def test_zscore_zero_stddev():
    # Should return 50 without division error
    assert _zscore_to_100(10.0, 10.0, 0.0, 3.0) == 50.0


@pytest.mark.parametrize("score,expected_label", [
    (85, "CRITICAL"),
    (65, "HIGH"),
    (45, "ELEVATED"),
    (25, "GUARDED"),
    (10, "NORMAL"),
])
def test_severity_labels(score, expected_label):
    label, _ = _severity(score)
    assert label == expected_label
