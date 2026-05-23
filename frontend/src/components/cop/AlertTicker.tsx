"use client";
import { useCOPStore } from "@/store/cop-store";
const sevColor = (s: string) => s === "critical" ? "text-red-400" : s === "high" ? "text-yellow-400" : "text-blue-400";
export default function AlertTicker() {
  const { state } = useCOPStore();
  return (
    <div className="bg-gray-900 rounded p-2 border border-gray-700">
      <div className="text-xs font-bold text-gray-400 mb-1">ALERTS</div>
      {state.alerts.slice(0, 5).map(a => (
        <div key={a.id} className="text-xs font-mono flex gap-2 border-b border-gray-800 py-0.5">
          <span className={sevColor(a.severity)}>{a.severity.toUpperCase()}</span>
          <span className="text-gray-300">{a.message}</span>
        </div>
      ))}
    </div>
  );
}
