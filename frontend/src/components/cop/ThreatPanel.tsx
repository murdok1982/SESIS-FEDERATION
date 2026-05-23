"use client";
import { useCOPStore } from "@/store/cop-store";
export default function ThreatPanel() {
  const { state } = useCOPStore();
  return (
    <div className="bg-gray-900 rounded p-2 border border-gray-700">
      <div className="text-xs font-bold text-gray-400 mb-1">THREAT ASSESSMENT</div>
      {state.threats.slice(0, 3).map(t => (
        <div key={t.id} className="text-xs font-mono py-0.5">
          <span className="text-red-400">{t.target}</span>
          <div className="w-full bg-gray-700 h-1 mt-0.5">
            <div className="bg-red-500 h-1" style={{width: \`\${t.confidence * 100}%\`}} />
          </div>
        </div>
      ))}
    </div>
  );
}
