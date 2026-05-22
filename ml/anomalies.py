"""
Anomaly Detection Module — Actualizado con Isolation Forest.
Sustituye Z-score por detección más robusta.
"""
import numpy as np
from typing import List, Dict, Any, Optional
import logging

from ml.isolation_forest import IsolationForestDetector

logger = logging.getLogger("sesis.ml.anomalies")

# Detectores por parámetro
_detectors = {}


def detect_anomalies(
    data_points: List[Dict[str, Any]],
    parameter: str,
    window_size: int = 100
) -> List[Dict[str, Any]]:
    """
    Detecta anomalías usando Isolation Forest (mejor que Z-score).
    """
    if len(data_points) < 10:
        return []

    if parameter not in _detectors:
        _detectors[parameter] = IsolationForestDetector(
            contamination=0.1,
            random_state=42
        )

    return _detectors[parameter].detect(data_points, parameter, window_size)


def detect_geo_anomaly(
    lat: float,
    lon: float,
    asset_id: str,
    historical: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Detecta anomalías geográficas (saltos imposibles).
    """
    if not historical:
        return None

    # Obtener última posición
    last_point = historical[-1]
    last_lat = last_point.get("lat")
    last_lon = last_point.get("lon")

    if last_lat is None or last_lon is None:
        return None

    # Calcular distancia Haversine
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # km
    lat1, lon1 = radians(last_lat), radians(last_lon)
    lat2, lon2 = radians(lat), radians(lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance_km = R * c

    import time
    current_time = time.time()
    last_time = last_point.get("timestamp", current_time - 3600)
    time_diff_hours = max(0.01, (current_time - last_time) / 3600.0) # Evitar div 0
    speed_kmh = distance_km / time_diff_hours

    if speed_kmh > 500:  # Velocidad imposible para activo terrestre
        return {
            "is_anomaly": True,
            "anomaly_type": "GEO_JUMP",
            "distance_km": distance_km,
            "speed_kmh": speed_kmh,
            "threshold_km": 100,
            "severity": "CRITICAL" if speed_kmh > 1000 else "HIGH",
            "asset_id": asset_id
        }

    return None


def detect_telemetry_spike(
    current_value: float,
    parameter: str,
    historical: List[float],
    threshold_std: float = 3.0
) -> Optional[Dict[str, Any]]:
    """
    Detecta picos en telemetría (ej: temperatura, vibración).
    """
    if len(historical) < 10:
        return None

    values = np.array(historical)
    mean = np.mean(values)
    std = np.std(values)

    z_score = abs(current_value - mean) / std if std > 0 else 0

    if z_score > threshold_std:
        return {
            "is_anomaly": True,
            "anomaly_type": "TELEMETRY_SPIKE",
            "parameter": parameter,
            "current_value": current_value,
            "mean": float(mean),
            "std": float(std),
            "z_score": float(z_score),
            "severity": "HIGH" if z_score > 5 else "MEDIUM"
        }

    return None
