from __future__ import annotations

import hashlib
import io
import time

import httpx

from app.services.osint.tools.base import ToolBase, ToolResult

MAX_SIZE = 52_428_800  # 50MB

class DocumentExtractTool(ToolBase):
    name = "document_extract"
    description = "Extract text and metadata from public documents (PDF, DOCX, images)"
    rate_limit_per_minute = 20

    def __init__(self, config=None) -> None:
        self.config = config

    async def execute(self, url: str | None = None, file_path: str | None = None) -> ToolResult:
        await self._rate_limit_check()
        t0 = time.monotonic()

        content = b""
        source = url or file_path or ""

        if url:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, follow_redirects=True)
                    resp.raise_for_status()
                    content = resp.content
                    if len(content) > MAX_SIZE:
                        return ToolResult(success=False, data=None, source=url, method="document_extract", error="File too large")
                    content_type = resp.headers.get("content-type", "")
            except Exception as exc:
                return ToolResult(success=False, data=None, source=url, method="document_extract", error=str(exc))
        elif file_path:
            try:
                with open(file_path, "rb") as f:
                    content = f.read(MAX_SIZE)
                content_type = ""
            except Exception as exc:
                return ToolResult(success=False, data=None, source=file_path, method="document_extract", error=str(exc))
        else:
            return ToolResult(success=False, data=None, source="", method="document_extract", error="No source provided")

        sha256 = hashlib.sha256(content).hexdigest()
        file_type = self._detect_type(content)
        text = ""
        metadata: dict = {}

        if file_type == "pdf":
            try:
                from pypdf import PdfReader  # noqa: PLC0415
                reader = PdfReader(io.BytesIO(content))
                text = "\n".join(page.extract_text() or "" for page in reader.pages[:50])
                info = reader.metadata or {}
                metadata = {k: str(v) for k, v in info.items() if v}
            except Exception:
                pass
        elif file_type == "docx":
            try:
                import docx  # noqa: PLC0415
                doc = docx.Document(io.BytesIO(content))
                text = "\n".join(p.text for p in doc.paragraphs)
                core = doc.core_properties
                metadata = {"author": core.author or "", "title": core.title or "", "created": str(core.created or "")}
            except Exception:
                pass
        elif file_type in ("jpeg", "png", "tiff"):
            try:
                import piexif  # noqa: PLC0415
                exif_data = piexif.load(content)
                metadata["exif"] = {str(k): str(v) for k, v in exif_data.items() if v}
            except Exception:
                pass

        return ToolResult(
            success=True,
            data={
                "sha256": sha256,
                "file_type": file_type,
                "size_bytes": len(content),
                "text": text[:10000],
                "metadata": metadata,
                "source": source,
            },
            source=source,
            method="document_extract",
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    def _detect_type(self, content: bytes) -> str:
        magic = content[:8]
        if magic[:4] == b"%PDF":
            return "pdf"
        if magic[:4] == b"PK\x03\x04":
            return "docx"
        if magic[:3] == b"\xff\xd8\xff":
            return "jpeg"
        if magic[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"
        if magic[:4] in (b"II*\x00", b"MM\x00*"):
            return "tiff"
        return "unknown"
