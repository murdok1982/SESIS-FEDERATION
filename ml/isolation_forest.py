"""
Isolation Forest Anomaly Detector — Mejor que Z-score para patrones complejos.
Detección no supervisada de anomalías en telemetría militar.
"""
import numpy as np
from sklearn.ensemble import IsolationForest
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("sesis.ml.anomalies")


class IsolationForestDetector:
    """Detector de anomalías usando Isolation Forest."""

    def __init__(self, contamination: float = 0.1, random_state: int = 42):
        """
        Args:
            contamination: Proporción esperada de anomalías (0.1 = 10%)
            random_state: Semilla para reproducibilidad
        """
        self.contamination = contamination
        self.random_state = random_state
        self.models = {}  # Un modelo por tipo de telemetría

    def detect(
        self,
        data_points: List[Dict[str, Any]],
        parameter: str,
        window_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Detecta anomalías en serie temporal.
        Retorna lista de puntos marcados como anomalías.
        """
        if len(data_points) < 10:
            return []

        values = np.array([p.get("value", 0) for p in data_points]).reshape(-1, 1)

        # Entrenar o actualizar modelo (Solo fit inicial en la vía caliente)
        if parameter not in self.models:
            self.models[parameter] = IsolationForest(
                contamination=self.contamination,
                random_state=self.random_state,
                n_estimators=100
            )
            self.models[parameter].fit(values)
        # NOTA: En producción, un worker de background debería llamar a self.models[parameter].fit periódicamente
        # No hacemos fit en cada detect para no colapsar la CPU y el Event Loop.

        # Predecir (-1 = anomalía, 1 = normal)
        predictions = self.models[parameter].predict(values)
        scores = self.models[parameter].decision_function(values)

        anomalies = []
        for idx, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:  # Anomalía
                anomalies.append({
                    "index": idx,
                    "data": data_points[idx],
                    "anomaly_score": float(score),
                    "severity": "HIGH" if score < -0.5 else "MEDIUM"
                })
                logger.warning(
                    f"Anomalía detectada en {parameter}: score={score:.3f}, "
                    f"valor={data_points[idx].get('value')}"
                )

        return anomalies

    def detect_geo_anomaly(
        self,
        lat: float,
        lon: float,
        historical_positions: List[tuple[float, float]]
    ) -> Optional[Dict[str, Any]]:
        """
        Detecta anomalías geográficas (saltos imposibles).
        Usa distancia Haversine para validar velocidad.
        """
        if not historical_positions:
            return None

        last_lat, last_lon = historical_positions[-1]

        # Calcular distancia Haversine
        from math import radians, sin, cos, sqrt, atan2
        R = 6371  # Radio Tierra km

        lat1, lon1 = radians(last_lat), radians(last_lon)
        lat2, lon2 = radians(lat), radians(lon)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        distance_km = R * c

        # Si distancia > 100km y tiempo < 1 hora = anomalía
        return {
            "is_anomaly": distance_km > 100,
            "distance_km": distance_km,
            "threshold_km": 100,
            "severity": "CRITICAL" if distance_km > 500 else "HIGH"
        } if distance_km > 100 else None
