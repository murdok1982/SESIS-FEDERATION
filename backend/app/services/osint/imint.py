from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings, get_settings

logger = get_logger(__name__)

@dataclass
class ImageAnalysisResult:
    image_hash: str
    exif_data: dict[str, Any] = field(default_factory=dict)
    gps_coordinates: tuple[float, float] | None = None
    dominant_colors: list[str] = field(default_factory=list)
    detected_objects: list[str] = field(default_factory=list)
    ocr_text: str = ""
    reverse_search_results: list[str] = field(default_factory=list)
    manipulation_detected: bool = False
    risk_score: float = 0.0

class IMINTModule:
    """Image Intelligence module for visual analysis and geolocation."""

    def __init__(self) -> None:
        pass

    async def analyze_image(self, image_data: bytes) -> ImageAnalysisResult:
        image_hash = hashlib.sha256(image_data).hexdigest()[:16]
        result = ImageAnalysisResult(image_hash=image_hash)

        result.exif_data = self._extract_exif(image_data)
        if result.exif_data.get("GPSLatitude") and result.exif_data.get("GPSLongitude"):
            result.gps_coordinates = (
                result.exif_data["GPSLatitude"],
                result.exif_data["GPSLongitude"],
            )

        result.dominant_colors = self._extract_dominant_colors(image_data)
        result.ocr_text = await self._extract_ocr(image_data)
        result.detected_objects = await self._detect_objects(image_data)
        result.manipulation_detected = self._detect_manipulation(image_data)
        result.reverse_search_results = await self._reverse_search(image_data)
        result.risk_score = self._calculate_image_risk(result)

        return result

    def _extract_exif(self, image_data: bytes) -> dict[str, Any]:
        try:
            import piexif
            exif_dict = piexif.load(io.BytesIO(image_data))
            exif_data = {}
            for ifd_name in exif_dict:
                for tag_name, tag_value in exif_dict[ifd_name].items():
                    tag_str = str(tag_value)[:200]
                    exif_data[str(tag_name)] = tag_str
            if "GPS" in exif_dict:
                gps = exif_dict["GPS"]
                if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
                    lat = self._convert_to_degrees(gps[piexif.GPSIFD.GPSLatitude])
                    lon = self._convert_to_degrees(gps[piexif.GPSIFD.GPSLongitude])
                    exif_data["GPSLatitude"] = lat
                    exif_data["GPSLongitude"] = lon
            return exif_data
        except Exception as exc:
            logger.warning("exif_extraction_failed", error=str(exc))
            return {}

    def _convert_to_degrees(self, value: tuple) -> float:
        try:
            d = value[0][0] / value[0][1]
            m = value[1][0] / value[1][1]
            s = value[2][0] / value[2][1]
            return d + (m / 60.0) + (s / 3600.0)
        except (ZeroDivisionError, IndexError):
            return 0.0

    def _extract_dominant_colors(self, image_data: bytes) -> list[str]:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            img = img.resize((100, 100))
            colors = img.getcolors(256 * 256)
            if colors:
                sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
                return [f"#{r:02x}{g:02x}{b:02x}" for _, (r, g, b) in sorted_colors[:5]]
        except Exception as exc:
            logger.warning("color_extraction_failed", error=str(exc))
        return []

    async def _extract_ocr(self, image_data: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(image_data))
            return pytesseract.image_to_string(img, lang="eng+spa")[:5000]
        except Exception as exc:
            logger.warning("ocr_extraction_failed", error=str(exc))
            return ""

    async def _detect_objects(self, image_data: bytes) -> list[str]:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_data))
            return [f"image_{img.format}", f"size_{img.size[0]}x{img.size[1]}"]
        except Exception:
            return []

    def _detect_manipulation(self, image_data: bytes) -> bool:
        try:
            import piexif
            exif_dict = piexif.load(io.BytesIO(image_data))
            if "Software" in exif_dict.get("0th", {}):
                software = str(exif_dict["0th"].get(piexif.ImageIFD.Software, ""))
                editing_software = ["photoshop", "gimp", "affinity", "paint.net"]
                return any(soft in software.lower() for soft in editing_software)
        except Exception:
            pass
        return False

    async def _reverse_search(self, image_data: bytes) -> list[str]:
        return []

    def _calculate_image_risk(self, result: ImageAnalysisResult) -> float:
        score = 0.0
        if result.gps_coordinates:
            score += 3.0
        if result.exif_data.get("Make") or result.exif_data.get("Model"):
            score += 1.0
        if result.manipulation_detected:
            score += 4.0
        if result.ocr_text:
            sensitive_words = ["confidential", "secret", "classified", "internal", "restricted"]
            for word in sensitive_words:
                if word in result.ocr_text.lower():
                    score += 2.0
        return min(score, 10.0)

imint = IMINTModule()
