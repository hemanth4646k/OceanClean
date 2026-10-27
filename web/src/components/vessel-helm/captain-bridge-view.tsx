import React from 'react';
import {
  Anchor,
  BatteryCharging,
  Gauge,
  Layers,
  Ship,
  ShieldAlert,
} from 'lucide-react';
import { Vessel, InterceptionRoute, CurrentGridPoint } from '../../types/marine';
import { CurrentAssistDial } from './current-assist-dial';
import { WaypointQueueCard } from './waypoint-queue-card';

interface CaptainBridgeViewProps {
  vessels: Vessel[];
  selectedVessel: Vessel | null;
  onSelectVessel: (v: Vessel) => void;
  routes: InterceptionRoute[];
  onWaypointCompleted: () => void;
  currentsGrid: CurrentGridPoint[];
}

export const CaptainBridgeView: React.FC<CaptainBridgeViewProps> = ({
  vessels,
  selectedVessel,
  onSelectVessel,
  routes,
  onWaypointCompleted,
  currentsGrid,
}) => {
  const currentVessel = selectedVessel || vessels[0];
  const activeRoute = routes.find((r) => r.vesselId === currentVessel?.id);

  if (!currentVessel) {
    return null;
  }

  const loadPct = Math.round(
    ((currentVessel.currentLoadTons || 0) / currentVessel.maxCapacityTons) * 100,
  );

  // Approximate local ocean current for this vessel from the currents grid
  const nearestCurrent = currentsGrid[0] || {
    direction_deg: 90.0,
    velocity_ms: 1.2,
    wave_height_m: 1.8,
  };

  return (
    <div className="fixed top-20 right-4 z-30 w-96 hud-panel rounded-2xl p-4 space-y-4 shadow-2xl max-h-[85vh] overflow-y-auto">
      {/* Vessel Selector Dropdown */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <Ship className="w-5 h-5 text-emerald-400" />
          <h2 className="text-xs font-bold font-mono tracking-wide text-slate-100 uppercase">
            Tactical Bridge Helm
          </h2>
        </div>
        <select
          value={currentVessel.id}
          onChange={(e) => {
            const chosen = vessels.find((v) => v.id === e.target.value);
            if (chosen) onSelectVessel(chosen);
          }}
          className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1 font-mono focus:outline-none focus:border-cyan-400"
        >
          {vessels.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.callsign})
            </option>
          ))}
        </select>
      </div>

      {/* Onboard Status Counters */}
      <div className="grid grid-cols-2 gap-3 text-xs font-mono">
        {/* Storage Load */}
        <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[10px]">
            <span>Storage Bay</span>
            <span>{loadPct}% Full</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                loadPct > 80 ? 'bg-red-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.min(100, loadPct)}%` }}
            />
          </div>
          <div className="text-[11px] font-bold text-slate-200 flex justify-between pt-0.5">
            <span>{currentVessel.currentLoadTons.toFixed(1)}t</span>
            <span className="text-slate-500">/ {currentVessel.maxCapacityTons}t max</span>
          </div>
        </div>

        {/* Marine Fuel */}
        <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-[10px]">
            <span>Fuel Bunker</span>
            <span>{currentVessel.fuelLevelPct.toFixed(0)}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-cyan-400"
              style={{ width: `${currentVessel.fuelLevelPct}%` }}
            />
          </div>
          <div className="text-[11px] font-bold text-cyan-300 flex justify-between pt-0.5">
            <span>{currentVessel.cruiseSpeedKnots} kts</span>
            <span className="text-slate-500">Cruise Spd</span>
          </div>
        </div>
      </div>

      {/* Current-Assist Compass Dial */}
      <CurrentAssistDial
        vesselHeadingDeg={90.0}
        currentDirectionDeg={nearestCurrent.direction_deg}
        currentVelocityMs={nearestCurrent.velocity_ms}
      />

      {/* Interception Waypoint Queue Card */}
      <WaypointQueueCard
        route={activeRoute}
        onWaypointCompleted={onWaypointCompleted}
      />
    </div>
  );
};

