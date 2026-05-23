"use client";
import { useState } from "react";
const LEVELS = ["UNCLASSIFIED", "RESTRICTED", "CONFIDENTIAL", "SECRET", "TOP SECRET"];
export default function ClassificationBanner() {
  const [level, setLevel] = useState(1);
  const colors = ["bg-green-700", "bg-blue-700", "bg-yellow-600", "bg-red-700", "bg-purple-800"];
  return (
    <div className={\`\${colors[level]} text-white text-center text-xs font-mono py-1 tracking-widest\`}>
      {LEVELS[level]} — SESIS-FEDERATION C4ISR — {LEVELS[level]}
    </div>
  );
}
