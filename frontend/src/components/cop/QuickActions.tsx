export default function QuickActions() {
  const actions = [
    { label: "OPORD", icon: "O", desc: "Generate OPORD" },
    { label: "COA", icon: "W", desc: "Run COA Sim" },
    { label: "BDA", icon: "B", desc: "Request BDA" },
    { label: "TASK", icon: "T", desc: "New Task" },
  ];
  return (
    <div className="flex gap-2">
      {actions.map(a => (
        <button key={a.label}
          className="bg-gray-800 hover:bg-gray-700 text-green-400 text-xs font-mono px-3 py-1.5 rounded border border-gray-600">
          [{a.icon}] {a.desc}
        </button>
      ))}
    </div>
  );
}
