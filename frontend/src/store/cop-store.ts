import { create } from "zustand";
import { COPState } from "@/lib/cop-types";

const defaultModules = [
  { id: "c2", name: "C2", status: "operational" as const, color: "text-green-400" },
  { id: "satellite", name: "Satellite", status: "operational" as const, color: "text-green-400" },
  { id: "osint", name: "OSINT", status: "operational" as const, color: "text-green-400" },
  { id: "intel", name: "Intel", status: "operational" as const, color: "text-green-400" },
  { id: "agents", name: "Agents", status: "operational" as const, color: "text-green-400" },
  { id: "tactical", name: "Tactical", status: "operational" as const, color: "text-green-400" },
  { id: "sensors", name: "Sensors", status: "operational" as const, color: "text-green-400" },
  { id: "ml", name: "ML", status: "operational" as const, color: "text-green-400" },
  { id: "cop", name: "COP", status: "operational" as const, color: "text-green-400" },
];

export const useCOPStore = create<{
  state: COPState;
  addAlert: (a: any) => void;
  addIntel: (i: any) => void;
  addThreat: (t: any) => void;
  addEvent: (e: any) => void;
  setModuleStatus: (id: string, status: any) => void;
  getAlertsBySeverity: (s: string) => any[];
}>(set => ({
  state: {
    alerts: [], units: [], intelFeed: [], threats: [], bdaReports: [],
    agentReports: [], psyopsMessages: [], sensors: [], wargamingResults: [],
    timeline: [], modules: defaultModules,
  },
  addAlert: (a) => set(s => ({ state: { ...s.state, alerts: [a, ...s.state.alerts].slice(0, 100) } })),
  addIntel: (i) => set(s => ({ state: { ...s.state, intelFeed: [i, ...s.state.intelFeed].slice(0, 50) } })),
  addThreat: (t) => set(s => ({ state: { ...s.state, threats: [t, ...s.state.threats].slice(0, 20) } })),
  addEvent: (e) => set(s => ({ state: { ...s.state, timeline: [e, ...s.state.timeline].slice(0, 200) } })),
  setModuleStatus: (id, status) => set(s => ({
    state: {
      ...s.state,
      modules: s.state.modules.map(m => m.id === id ? { ...m, status } : m),
    },
  })),
  getAlertsBySeverity: (severity) => [],
}));
