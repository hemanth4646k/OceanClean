import React, { useState } from 'react';
import { CheckCircle, Navigation, Loader2 } from 'lucide-react';
import { InterceptionRoute, RouteWaypoint } from '../../types/marine';
import { apiClient } from '../../lib/api-client';

interface WaypointQueueCardProps {
  route?: InterceptionRoute;
  onWaypointCompleted: () => void;
}

export const WaypointQueueCard: React.FC<WaypointQueueCardProps> = ({
  route,
  onWaypointCompleted,
}) => {
  const [clearingH3, setClearingH3] = useState<string | null>(null);

  if (!route || !route.waypointsJson || route.waypointsJson.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center font-mono">
        <Navigation className="w-6 h-6 text-slate-500 mx-auto mb-1.5" />
        <p className="text-xs text-slate-400">No active interception waypoints assigned.</p>
        <p className="text-[10px] text-slate-500">Run OR-Tools optimizer from Commander HUD</p>
      </div>
    );
  }

  const handleHarvest = async (wp: RouteWaypoint) => {
    try {
      setClearingH3(wp.h3Index);
      await apiClient.completeWaypoint(route.id, wp.h3Index);
      onWaypointCompleted();
    } catch (err: any) {
      console.error(`Harvesting waypoint ${wp.h3Index} failed:`, err);
    } finally {
      setClearingH3(null);
    }
  };

  return (
    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3 font-mono">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-200">
          <Navigation className="w-4 h-4 text-emerald-400" />
          <span>Interception Waypoint Manifest</span>
        </div>
        <span className="text-[10px] text-emerald-400">
          {route.waypointsJson.filter((w) => w.completed).length} / {route.waypointsJson.length} Harvested
        </span>
      </div>

      <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
        {route.waypointsJson.map((wp, idx) => (
          <div
            key={wp.h3Index || idx}
            className={`p-2.5 rounded-lg border text-xs flex items-center justify-between transition-all ${
              wp.completed
                ? 'bg-slate-950/40 border-slate-800/80 text-slate-500'
                : 'bg-slate-900/80 border-slate-700/80 text-slate-200'
            }`}
          >
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-cyan-400">#{idx + 1}</span>
                <span className="font-bold">{wp.h3Index.slice(0, 9)}...</span>
                {wp.completed && (
                  <span className="text-[10px] text-emerald-400 font-semibold flex items-center space-x-0.5">
                    <CheckCircle className="w-3 h-3 inline" />
                    <span>CLEARED</span>
                  </span>
                )}
              </div>
              <div className="text-[10px] text-slate-400 flex space-x-3 mt-0.5">
                <span>Dist: {wp.distanceNm} NM</span>
                <span>Fuel: {wp.estimatedFuelLiters} L</span>
                <span className="text-red-400 font-semibold">
                  Yield: {((wp.estimatedMassKg || 0) / 1000).toFixed(1)} t
                </span>
              </div>
            </div>

            {!wp.completed && (
              <button
                onClick={() => handleHarvest(wp)}
                disabled={clearingH3 !== null}
                className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-[10px] font-bold shadow-md shadow-emerald-600/30 transition-all flex items-center space-x-1"
              >
                {clearingH3 === wp.h3Index ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <span>Harvest & Clear</span>
                )}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

