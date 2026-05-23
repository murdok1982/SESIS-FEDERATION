export interface Alert {
  id: string; severity: "critical" | "high" | "medium" | "low"
  source: string; message: string; timestamp: string; acknowledged: boolean
}
export interface UnitPosition { id: string; name: string; type: string; lat: number; lon: number; status: string }
export interface IntelReport { id: string; title: string; classification: string; source: string; confidence: number; timestamp: string }
export interface ThreatAssessment { id: string; target: string; severity: number; confidence: number; recommended_action: string }
export interface BDAReport { strike_id: string; effectiveness: number; collateral: boolean; sources: string[] }
export interface AgentReport { id: string; agent: string; mission: string; status: string; location?: string }
export interface PSYOPSMessage { id: string; campaign: string; message: string; effectiveness: number }
export interface SensorNode { id: string; type: string; battery: number; status: string; last_reading?: string }
export interface WargamingResult { coa: string; success_probability: number; casualties: number; duration_hours: number }
export interface MissionEvent { id: string; type: string; description: string; timestamp: string; severity: string }
export interface COPModule { id: string; name: string; status: "operational" | "degraded" | "offline"; color: string }
export interface COPState {
  alerts: Alert[]; units: UnitPosition[]; intelFeed: IntelReport[]
  threats: ThreatAssessment[]; bdaReports: BDAReport[]; agentReports: AgentReport[]
  psyopsMessages: PSYOPSMessage[]; sensors: SensorNode[]; wargamingResults: WargamingResult[]
  timeline: MissionEvent[]; modules: COPModule[]
}
