# -*- coding: utf-8 -*-
"""
HISPANSHIELD — GUARDIÁN DE PROPIEDAD INTELECTUAL
══════════════════════════════════════════════════
Propiedad de HispanShield (Legión de Ciberdefensa)
General Murdok (Gustavo Lobato Clara)
Cualquier uso no autorizado será perseguido legalmente.
══════════════════════════════════════════════════
"""
import os
import sys
import socket
import getpass
import platform
import hashlib
import json
from datetime import datetime, timezone

__version__ = "1.0.0"
__author__ = "HispanShield — Legión de Ciberdefensa"
__copyright__ = "Copyright 2026 — General Murdok (Gustavo Lobato Clara)"

FINGERPRINT = hashlib.sha256(f"{__copyright__}-{__version__}".encode()).hexdigest()

SEAL = """
╔══════════════════════════════════════════════════════════════╗
║       HISPANSHIELD — LEGIÓN DE CIBERDEFENSA               ║
║       PROPIEDAD DE GENERAL MURDOK (GUSTAVO LOBATO CLARA)  ║
║       TODOS LOS DERECHOS RESERVADOS                        ║
║       CUALQUIER USO NO AUTORIZADO SERÁ PERSEGUIDO          ║
║       BAJO PENA DE LEY                                     ║
╚══════════════════════════════════════════════════════════════╝
"""


def audit_trail() -> dict:
    """Captura información del entorno para auditoría."""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    except Exception:
        hostname = "unknown"
        ip = "0.0.0.0"

    return {
        "_hispan_shield_fingerprint": FINGERPRINT,
        "usuario": getpass.getuser(),
        "hostname": hostname,
        "ip_address": ip,
        "plataforma": platform.platform(),
        "python_version": sys.version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "propiedad": "HispanShield — Legión de Ciberdefensa",
        "titular": "General Murdok (Gustavo Lobato Clara)",
    }


def guardian_init():
    """Inicializa el guardián y muestra el sello de propiedad."""
    info = audit_trail()
    print(SEAL, file=sys.stderr)
    print(f"  Registro de auditoría:", file=sys.stderr)
    print(f"  Usuario:     {info['usuario']}", file=sys.stderr)
    print(f"  Hostname:    {info['hostname']}", file=sys.stderr)
    print(f"  IP:          {info['ip_address']}", file=sys.stderr)
    print(f"  Fecha UTC:   {info['timestamp_utc']}", file=sys.stderr)
    print(file=sys.stderr)
    return info


# Auto-ejecutar al importar
_g_audit = guardian_init()
