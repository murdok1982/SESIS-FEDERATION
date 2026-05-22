import numpy as np


def detect_anomalies_series(series: list, threshold: float = 2.0) -> list:
    arr = np.array(series)
    mean, std = np.mean(arr), np.std(arr)
    return [int(i) for i, v in enumerate(series) if abs(v - mean) > threshold * std]
