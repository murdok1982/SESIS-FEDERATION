import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0a0e17", foreground: "#e5e7eb",
        military: { green: "#3ddc84", blue: "#3498db", red: "#e94560", amber: "#f59e0b" },
      },
      fontFamily: { mono: ["Courier New", "monospace"] },
    },
  },
  plugins: [],
};
export default config;
