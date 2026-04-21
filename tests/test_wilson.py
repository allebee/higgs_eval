"""Wilson CI sanity checks."""
from drleval.reporter import wilson_ci


def test_wilson_bounds_all_pass():
    lo, hi = wilson_ci(5, 5)
    assert hi == 1.0
    assert lo > 0.5


def test_wilson_bounds_all_fail():
    lo, hi = wilson_ci(0, 5)
    assert lo == 0.0
    assert hi < 0.5


def test_wilson_empty():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_center():
    lo, hi = wilson_ci(3, 5)
    assert lo < 0.6 < hi
    # Interval width is meaningful at small N.
    assert hi - lo > 0.3
