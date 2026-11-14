"""Temperature scaling (Guo et al. 2017): one scalar T fitted on validation logits."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar


def _nll(logits: np.ndarray, y: np.ndarray, t: float) -> float:
    z = logits / t
    return float(np.mean(np.logaddexp(0, z) - y * z))


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    logits, y = np.asarray(logits, float), np.asarray(y, float)
    res = minimize_scalar(lambda lt: _nll(logits, y, np.exp(lt)), bounds=(-3, 3), method="bounded")
    return float(np.exp(res.x))


def apply_temperature(logits: np.ndarray, t: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(logits, float) / t))
