import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(222 47% 11%)",
        foreground: "hsl(210 40% 98%)",
        military: { green: "#3ddc84", blue: "#3498db", red: "#e94560" },
      },
    },
  },
  plugins: [],
};
export default config;
