"use client";
import ClassificationBanner from "./ClassificationBanner";
import StatusBar from "./StatusBar";
import MissionClock from "./MissionClock";
import AlertTicker from "./AlertTicker";
import IntelFeed from "./IntelFeed";
import ThreatPanel from "./ThreatPanel";
import CommandInput from "./CommandInput";
import QuickActions from "./QuickActions";

export default function COPPage() {
  return (
    <div className="min-h-screen bg-[#0a0e17] flex flex-col">
      <ClassificationBanner />
      <div className="flex justify-between items-center px-4 py-1 bg-gray-950 border-b border-gray-800">
        <span className="text-green-400 font-bold text-sm">SESIS-FEDERATION COP</span>
        <MissionClock />
      </div>
      <StatusBar />
      <div className="flex-1 grid grid-cols-12 gap-2 p-2">
        {/* Left Panel — C2 */}
        <div className="col-span-3 flex flex-col gap-2">
          <div className="bg-gray-900 rounded p-2 border border-gray-700" style={{minHeight: "300px"}}>
            <div className="text-xs font-bold text-gray-400 mb-1">TACTICAL MAP</div>
            <div className="bg-gray-800 rounded flex items-center justify-center text-gray-600 text-xs" style={{height: "250px"}}>
              [Mapa Tactico — Leaflet/Mapbox]
            </div>
          </div>
          <AlertTicker />
        </div>
        {/* Center — Main COP */}
        <div className="col-span-6 flex flex-col gap-2">
          <IntelFeed />
          <ThreatPanel />
          <div className="bg-gray-900 rounded p-2 border border-gray-700">
            <div className="text-xs font-bold text-gray-400 mb-1">MISSION TIMELINE</div>
            <div className="flex gap-1 text-xs font-mono text-gray-500">
              <span className="text-green-400">00:00</span> OPORD received
              <span className="text-gray-600 mx-1">|</span>
              <span className="text-yellow-400">+02:00</span> Insertion
              <span className="text-gray-600 mx-1">|</span>
              <span className="text-red-400">+04:00</span> Contact
            </div>
          </div>
        </div>
        {/* Right Panel — Intel + Agents */}
        <div className="col-span-3 flex flex-col gap-2">
          <div className="bg-gray-900 rounded p-2 border border-gray-700">
            <div className="text-xs font-bold text-gray-400 mb-1">LINK ANALYSIS</div>
            <div className="bg-gray-800 rounded flex items-center justify-center text-gray-600 text-xs" style={{height: "100px"}}>
              [Neo4j Graph]
            </div>
          </div>
          <div className="bg-gray-900 rounded p-2 border border-gray-700">
            <div className="text-xs font-bold text-gray-400 mb-1">SENSOR MESH</div>
            <div className="text-xs font-mono text-green-400">All sensors online</div>
          </div>
          <div className="bg-gray-900 rounded p-2 border border-gray-700">
            <div className="text-xs font-bold text-gray-400 mb-1">WARGAMING</div>
            <div className="text-xs font-mono text-gray-300">No active simulations</div>
          </div>
        </div>
      </div>
      {/* Bottom Bar */}
      <div className="border-t border-gray-800 p-2 bg-gray-950 flex gap-2 items-center">
        <QuickActions />
        <div className="flex-1" />
        <CommandInput />
      </div>
    </div>
  );
}
