"use client";
import { useState, useEffect } from "react";
export default function MissionClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(new Date().toISOString().slice(11, 19) + "Z");
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, []);
  return <span className="text-green-400 font-mono text-sm">{time}</span>;
}
