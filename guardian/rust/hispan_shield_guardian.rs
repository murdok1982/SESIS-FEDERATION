//==============================================================================
// HISPANSHIELD — GUARDIÁN DE PROPIEDAD INTELECTUAL
// Propiedad de HispanShield (Legión de Ciberdefensa)
// General Murdok (Gustavo Lobato Clara)
// Cualquier uso no autorizado será perseguido legalmente.
//==============================================================================

pub const HISPAN_VERSION: &str = "1.0.0";

pub fn hispan_shield_audit() {
    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown".to_string());

    eprintln!();
    eprintln!("╔══════════════════════════════════════════════════════════════╗");
    eprintln!("║       HISPANSHIELD — LEGIÓN DE CIBERDEFENSA               ║");
    eprintln!("║       PROPIEDAD DE GENERAL MURDOK (GUSTAVO LOBATO CLARA)  ║");
    eprintln!("║       TODOS LOS DERECHOS RESERVADOS                        ║");
    eprintln!("╚══════════════════════════════════════════════════════════════╝");
    eprintln!("  Auditoría: {}", hostname);
    eprintln!();
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_guardian() {
        hispan_shield_audit();
        assert_eq!(HISPAN_VERSION, "1.0.0");
    }
}
