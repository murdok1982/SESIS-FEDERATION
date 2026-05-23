#!/bin/bash
# =============================================================================
# HISPANSHIELD — GUARDIÁN DE PROPIEDAD INTELECTUAL
# Propiedad de HispanShield (Legión de Ciberdefensa)
# General Murdok (Gustavo Lobato Clara)
# Cualquier uso no autorizado será perseguido legalmente.
# =============================================================================

HISPAN_VERSION="1.0.0"
HISPAN_FINGERPRINT="$(echo "HispanShield-${HISPAN_VERSION}" | sha256sum | cut -d' ' -f1)"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       HISPANSHIELD — LEGIÓN DE CIBERDEFENSA               ║"
echo "║       PROPIEDAD DE GENERAL MURDOK (GUSTAVO LOBATO CLARA)  ║"
echo "║       TODOS LOS DERECHOS RESERVADOS                        ║"
echo "║       CUALQUIER USO NO AUTORIZADO SERÁ PERSEGUIDO          ║"
echo "║       BAJO PENA DE LEY                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Auditoría: usuario=$(whoami) | hostname=$(hostname) | ip=$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "  Fecha: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
