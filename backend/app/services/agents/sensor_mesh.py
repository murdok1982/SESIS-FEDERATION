from typing import Dict


class SensorMesh:
    """Red de sensores IoT militares."""

    SENSOR_TYPES = {
        "acoustic": {"range_km": 1.0, "battery_hours": 72},
        "seismic": {"range_km": 0.5, "battery_hours": 120},
        "rf_scanner": {"range_km": 5.0, "battery_hours": 48},
        "magnetic": {"range_km": 0.1, "battery_hours": 168},
        "chemical": {"range_km": 0.1, "battery_hours": 24},
    }

    def __init__(self):
        self.sensors: Dict[str, dict] = {}

    async def register_sensor(self, sensor_id: str, sensor_type: str, location: dict) -> Dict:
        if sensor_type not in self.SENSOR_TYPES:
            return {"status": "error", "reason": f"unknown sensor type: {sensor_type}"}
        self.sensors[sensor_id] = {"type": sensor_type, "location": location, "status": "active", "battery": 100}
        return {"status": "registered", "sensor_id": sensor_id}

    async def ingest_reading(self, sensor_id: str, reading: dict) -> Dict:
        if sensor_id not in self.sensors:
            return {"status": "error", "reason": "sensor not found"}
        self.sensors[sensor_id]["last_reading"] = reading
        return {"status": "ingested", "sensor_id": sensor_id}

    async def get_mesh_status(self) -> Dict:
        active = sum(1 for s in self.sensors.values() if s.get("status") == "active")
        return {"total": len(self.sensors), "active": active, "degraded": len(self.sensors) - active}

    async def route_sensor_data(self, source: str, target: str) -> bool:
        return source in self.sensors and target in self.sensors


sensor_mesh = SensorMesh()
