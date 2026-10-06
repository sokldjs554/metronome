from __future__ import annotations

import numpy as np
import pytest

from metronome.drift.detectors import ADWIN, PageHinkley, RatioRule, make_detector


def _stream(n_before: int, n_after: int, shift: float, seed: int = 0, noise: float = 0.01) -> list[float]:
    rng = np.random.default_rng(seed)
    a = 0.5 + rng.normal(0, noise, n_before)
    b = 0.5 + shift + rng.normal(0, noise, n_after)
    return list(np.r_[a, b])


def _first_alarm(det, xs: list[float]) -> int | None:
    for i, x in enumerate(xs):
        if det.update(x):
            return i
    return None


@pytest.mark.parametrize("spec", ["ratio-0.2", "ph-0.1", "adwin-0.01"])
def test_detectors_fire_after_a_level_shift_and_not_before(spec: str) -> None:
    xs = _stream(60, 80, shift=0.3)
    det = make_detector(spec, baseline=0.5)
    alarm = _first_alarm(det, xs)
    assert alarm is not None and 60 <= alarm < 140, (spec, alarm)
    quiet = make_detector(spec, baseline=0.5)
    assert _first_alarm(quiet, _stream(100, 0, 0.0)) is None, spec


def test_ratio_rule_waits_for_window_and_cooldown() -> None:
    det = RatioRule(tau=0.2, window=3, cooldown=5, baseline=1.0)
    assert [det.update(2.0) for _ in range(4)] == [False, False, False, False]  # cooldown=5 not reached
    assert det.update(2.0) is True
    det.reset(baseline=2.0)
    assert det.state()["baseline"] == 2.0 and det.state()["window_filled"] == 0
    assert not any(det.update(2.1) for _ in range(5))


def test_page_hinkley_statistic_is_nonnegative_and_resets() -> None:
    det = PageHinkley(lambda_=0.05, delta=0.0, min_samples=2)
    for x in [1.0, 1.0, 1.0]:
        det.update(x)
    assert det.state()["statistic"] >= 0
    fired = det.update(5.0)
    assert fired
    det.reset()
    assert det.state()["n"] == 0


def test_adwin_window_shrinks_on_change_and_tracks_mean() -> None:
    det = ADWIN(delta=0.01)
    for x in _stream(200, 0, 0.0):
        det.update(x)
    width_before = det.width
    assert width_before == 200 and abs(det.state()["mean"] - 0.5) < 0.02
    fired = [det.update(x) for x in _stream(0, 60, 0.4)]
    assert any(fired)
    assert det.width < width_before + 60
    assert det.state()["mean"] > 0.75  # window now dominated by post-shift values


def test_make_detector_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        make_detector("cusum-1")
