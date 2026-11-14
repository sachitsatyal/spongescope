import numpy as np

from spongescope.evaluation.calibration import apply_temperature, fit_temperature


def test_recovers_temperature():
    rng = np.random.default_rng(0)
    true_logit = rng.normal(0, 2, 20000)
    y = (rng.random(20000) < 1 / (1 + np.exp(-true_logit))).astype(float)
    t = fit_temperature(true_logit * 3.0, y)  # overconfident by 3x
    assert abs(t - 3.0) < 0.2
    p = apply_temperature(np.array([0.0, 6.0]), 3.0)
    assert abs(p[0] - 0.5) < 1e-9 and abs(p[1] - 1 / (1 + np.exp(-2))) < 1e-9
