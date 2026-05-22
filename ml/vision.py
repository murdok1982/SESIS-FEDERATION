"""
Vision Analyzer — YOLOv8 para análisis de imágenes satelitales/dron.
Detecta vehículos, instalaciones, tropas, equipo militar.
"""
from ultralytics import YOLO
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import tempfile
import base64
from PIL import Image
import io

logger = logging.getLogger("sesis.ml.vision")


class VisionAnalyzer:
    """Analizador de visión con YOLOv8 pre-entrenado."""

    # Clases militares de interés (COCO dataset + custom)
    MILITARY_CLASSES = {
        2: "car", 3: "motorcycle", 4: "airplane", 5: "bus",
        6: "train", 7: "truck", 8: "boat",
        # Clases personalizadas (si se entrena modelo custom)
        100: "tank", 101: "apc", 102: "artillery", 103: "radar"
    }

    def __init__(self, model_name: str = "yolov8n.pt"):
        """
        Inicializa con modelo YOLOv8.
        Opciones: yolov8n.pt (nano), yolov8s.pt (small), yolov8m.pt (medium)
        """
        try:
            self.model = YOLO(model_name)
            self.model_loaded = True
            logger.info(f"✅ YOLOv8 modelo cargado: {model_name}")
        except Exception as e:
            logger.error(f"❌ Error cargando YOLOv8: {e}")
            self.model = None
            self.model_loaded = False

    def analyze_image(
        self,
        image_data: bytes,
        confidence_threshold: float = 0.25
    ) -> Dict[str, Any]:
        """
        Analiza imagen satelital o de dron.
        Retorna detecciones con coordenadas y clasificación.
        """
        if not self.model_loaded:
            return self._fallback_response("Modelo YOLOv8 no disponible")

        try:
            # Inferencia en memoria
            image = Image.open(io.BytesIO(image_data))
            results = self.model(image, conf=confidence_threshold)[0]

            detections = []
            military_detections = []

            for box in results.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]

                class_name = self.MILITARY_CLASSES.get(cls_id, f"class_{cls_id}")

                detection = {
                    "class": class_name,
                    "confidence": conf,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],  # x, y, w, h
                    "is_military": cls_id in self.MILITARY_CLASSES
                }
                detections.append(detection)

                if detection["is_military"]:
                    military_detections.append(detection)

            # Generar resumen táctico
            summary = self._generate_tactical_summary(military_detections)

            return {
                "status": "success",
                "total_detections": len(detections),
                "military_detections": len(military_detections),
                "detections": detections[:20],  # Limitar a 20
                "military_summary": summary,
                "image_size": results.orig_shape
            }

        except Exception as e:
            logger.error(f"Error en análisis de imagen: {e}")
            return self._fallback_response(str(e))

    def analyze_satellite_image(
        self,
        image_data: bytes,
        geo_bounds: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Análisis especializado para imágenes satelitales.
        geo_bounds: {north, south, east, west} para mapear coordenadas.
        """
        result = self.analyze_image(image_data, confidence_threshold=0.3)

        if geo_bounds and result["status"] == "success":
            # Convertir coordenadas de pixel a geo
            img_h, img_w = result["image_size"]
            north = geo_bounds.get("north", 0)
            south = geo_bounds.get("south", 0)
            east = geo_bounds.get("east", 0)
            west = geo_bounds.get("west", 0)

            for det in result["detections"]:
                bbox = det["bbox"]
                # Conversión simplificada (asume proyección equirectangular)
                pixel_x = bbox[0] + bbox[2] / 2
                pixel_y = bbox[1] + bbox[3] / 2

                geo_lon = west + (pixel_x / img_w) * (east - west)
                geo_lat = north - (pixel_y / img_h) * (north - south)

                det["geo_position"] = {"lat": geo_lat, "lon": geo_lon}

        return result

    def _generate_tactical_summary(self, military_dets: List[Dict]) -> Dict[str, Any]:
        """Genera resumen táctico de detecciones militares."""
        summary = {
            "vehicles": 0,
            "aircraft": 0,
            "naval": 0,
            "infrastructure": 0,
            "threat_level": "LOW"
        }

        for det in military_dets:
            cls = det["class"]
            if cls in ["car", "truck", "tank", "apc"]:
                summary["vehicles"] += 1
            elif cls in ["airplane"]:
                summary["aircraft"] += 1
            elif cls in ["boat"]:
                summary["naval"] += 1
            elif cls in ["artillery", "radar"]:
                summary["infrastructure"] += 1

        # Determinar nivel de amenaza
        total = sum(summary.values())
        if total > 20:
            summary["threat_level"] = "HIGH"
        elif total > 10:
            summary["threat_level"] = "MEDIUM"

        return summary

    def _fallback_response(self, error: str) -> Dict[str, Any]:
        """Respuesta degradada cuando YOLOv8 no está disponible."""
        return {
            "status": "error",
            "message": "Vision analyzer no disponible (YOLOv8 requerido)",
            "error": error,
            "total_detections": 0,
            "military_detections": 0,
            "detections": [],
            "military_summary": {"threat_level": "UNKNOWN"}
        }
