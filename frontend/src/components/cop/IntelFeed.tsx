"use client";
import { useCOPStore } from "@/store/cop-store";
export default function IntelFeed() {
  const { state } = useCOPStore();
  return (
    <div className="bg-gray-900 rounded p-2 border border-gray-700">
      <div className="text-xs font-bold text-gray-400 mb-1">INTEL FEED</div>
      {state.intelFeed.slice(0, 5).map(i => (
        <div key={i.id} className="text-xs font-mono py-0.5">
          <span className="text-cyan-400">[{i.source}]</span>{" "}
          <span className="text-gray-300">{i.title}</span>
        </div>
      ))}
    </div>
  );
}
