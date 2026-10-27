import React from 'react';
import { Compass, TrendingUp, TrendingDown, Wind } from 'lucide-react';

interface CurrentAssistDialProps {
  vesselHeadingDeg: number;
  currentDirectionDeg: number;
  currentVelocityMs: number;
}

export const CurrentAssistDial: React.FC<CurrentAssistDialProps> = ({
  vesselHeadingDeg,
  currentDirectionDeg,
  currentVelocityMs,
}) => {
  // Dot product alignment between vessel heading and ocean current
  const headingRad = (vesselHeadingDeg * Math.PI) / 180.0;
  const currentRad = (currentDirectionDeg * Math.PI) / 180.0;
  const dotProduct = Math.cos(headingRad - currentRad); // in [-1, 1]

  // Beta factor 0.25 -> up to +25% fuel savings or -25% penalty
  const efficiencyBonusPct = dotProduct * 25.0 * (currentVelocityMs / 1.5);
  const isPositive = efficiencyBonusPct >= 0;

  return (
    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3 font-mono">
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-200">
          <Compass className="w-4 h-4 text-cyan-400" />
          <span>Current-Assist Dynamic Vector</span>
        </div>
        <span className="text-[10px] text-cyan-400/80">Open-Meteo Marine</span>
      </div>

      <div className="flex items-center justify-between">
        {/* Compass Graphic */}
        <div className="relative w-24 h-24 rounded-full border border-slate-700 bg-slate-950/80 flex items-center justify-center">
          {/* Compass Rose Labels */}
          <span className="absolute top-1 text-[9px] text-slate-500 font-bold">N</span>
          <span className="absolute bottom-1 text-[9px] text-slate-500 font-bold">S</span>
          <span className="absolute right-1 text-[9px] text-slate-500 font-bold">E</span>
          <span className="absolute left-1 text-[9px] text-slate-500 font-bold">W</span>

          {/* Ocean Current Vector (Cyan Arrow) */}
          <div
            className="absolute w-1 h-10 bg-cyan-400 rounded origin-bottom transform"
            style={{
              transform: `rotate(${currentDirectionDeg}deg) translateY(-50%)`,
              boxShadow: '0 0 8px #00f0ff',
            }}
          />

          {/* Vessel Heading Vector (Emerald / Amber Needle) */}
          <div
            className="absolute w-1.5 h-8 bg-emerald-400 rounded origin-bottom transform"
            style={{
              transform: `rotate(${vesselHeadingDeg}deg) translateY(-50%)`,
            }}
          />

          <div className="w-2.5 h-2.5 rounded-full bg-white z-10" />
        </div>

        {/* Readouts */}
        <div className="space-y-1 text-right text-xs">
          <div>
            <span className="text-[10px] text-slate-400 block">Vessel Heading</span>
            <span className="text-slate-100 font-bold">{vesselHeadingDeg.toFixed(0)}°</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block">Ocean Current</span>
            <span className="text-cyan-400 font-bold">
              {currentVelocityMs.toFixed(1)} m/s @ {currentDirectionDeg.toFixed(0)}°
            </span>
          </div>
        </div>
      </div>

      {/* Fuel Efficiency Badge */}
      <div
        className={`p-2 rounded-lg border flex items-center justify-between text-xs ${
          isPositive
            ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
            : 'bg-amber-950/40 border-amber-500/40 text-amber-300'
        }`}
      >
        <div className="flex items-center space-x-1.5">
          {isPositive ? (
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          ) : (
            <TrendingDown className="w-4 h-4 text-amber-400" />
          )}
          <span className="text-[11px] font-bold">
            {isPositive ? 'Riding Surface Current' : 'Opposing Head-Current'}
          </span>
        </div>
        <span className="font-bold">
          {isPositive ? `+${efficiencyBonusPct.toFixed(1)}%` : `${efficiencyBonusPct.toFixed(1)}%`} Fuel
        </span>
      </div>
    </div>
  );
};

