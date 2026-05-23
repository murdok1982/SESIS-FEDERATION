"use client";
import { useState } from "react";
export default function CommandInput() {
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const send = () => {
    if (!input.trim()) return;
    setHistory(h => [`> \${input}`, ...h]);
    setInput("");
  };
  return (
    <div className="bg-gray-900 rounded p-2 border border-gray-700">
      <div className="text-xs font-bold text-green-400 mb-1">fsociety LLM</div>
      <div className="max-h-20 overflow-y-auto mb-1">
        {history.slice(0, 5).map((h, i) => (
          <div key={i} className="text-xs font-mono text-gray-400">{h}</div>
        ))}
      </div>
      <div className="flex gap-1">
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          className="flex-1 bg-gray-800 text-green-400 text-xs font-mono p-1 rounded border border-gray-600 outline-none"
          placeholder="Comando para fsociety..." />
        <button onClick={send} className="bg-green-700 text-white text-xs px-2 rounded">ENVIAR</button>
      </div>
    </div>
  );
}
