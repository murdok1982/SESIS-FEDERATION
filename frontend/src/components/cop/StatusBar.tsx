"use client";
import { useCOPStore } from "@/store/cop-store";
const dotClass = (s: string) => s === "operational" ? "bg-green-400" : s === "degraded" ? "bg-yellow-400" : "bg-red-400";
export default function StatusBar() {
  const { state } = useCOPStore();
  return (
    <div className="flex gap-4 px-4 py-1 bg-gray-900 text-xs font-mono items-center border-b border-gray-700">
      {state.modules.map(m => (
        <div key={m.id} className="flex items-center gap-1">
          <span className={\`w-2 h-2 rounded-full \${dotClass(m.status)}\`} />
          <span className={m.color}>{m.name}</span>
        </div>
      ))}
    </div>
  );
}
