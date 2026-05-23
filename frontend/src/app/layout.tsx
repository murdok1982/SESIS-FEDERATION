import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "SESIS-FEDERATION C4ISR",
  description: "Common Operating Picture — Plataforma Unificada de Gobierno Digital Militar",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body className="bg-[#0a0e17] text-gray-100 m-0 p-0">{children}</body>
    </html>
  );
}
