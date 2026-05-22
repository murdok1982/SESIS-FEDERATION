export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body className="bg-background text-foreground">{children}</body>
    </html>
  );
}
