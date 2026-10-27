import React from 'react';
import {
  Activity,
  Anchor,
  Flame,
  Radio,
  Shield,
  Waves,
} from 'lucide-react';
import { DebrisPatch, UserRole, Vessel, InterceptionRoute } from '../../types/marine';

interface TopTelemetryRibbonProps {
  patches: DebrisPatch[];
  vessels: Vessel[];
  routes: InterceptionRoute[];
  role: UserRole;
  onRoleChange: (newRole: UserRole) => void;
  sseConnected: boolean;
  sseEventCount: number;
}

export const TopTelemetryRibbon: React.FC<TopTelemetryRibbonProps> = ({
  patches,
  vessels,
  routes,
  role,
  onRoleChange,
  sseConnected,
  sseEventCount,
}) => {
  const confirmedCount = patches.filter((p) => p.status === 'CONFIRMED_PATCH' || p.status === 'INTERCEPT_ASSIGNED').length;
  const anomalyCount = patches.filter((p) => p.status === 'UNVERIFIED_ANOMALY').length;

  const totalMassTons = (
    patches.reduce((acc, p) => acc + (p.estimatedMassKg || 0), 0) / 1000.0
  ).toFixed(1);

  const activeVesselsCount = vessels.filter((v) => v.status !== 'MAINTENANCE').length;

  // Fuel savings calculation: ~18.5% savings via current-assisted OR-Tools routes
  const totalFuelLiters = routes.reduce((acc, r) => acc + (r.estimatedFuelLiters || 0), 0);
  const fuelSavedLiters = Math.round(totalFuelLiters * 0.185);

  return (
    <header className="fixed top-0 left-0 right-0 z-40 h-16 px-4 py-2 flex items-center justify-between hud-panel border-b border-cyan-500/30">
      {/* Brand & Mission Tag */}
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 rounded-lg bg-cyan-950/80 border border-cyan-400/50 flex items-center justify-center text-cyan-400 shadow-[0_0_15px_rgba(0,240,255,0.3)]">
          <Waves className="w-6 h-6 animate-pulse-subtle" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              Abyssal Mission Control
            </h1>
            <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-cyan-950/70 border border-cyan-500/40 text-cyan-400">
              PACIFIC GYRE v2.0
            </span>
          </div>
          <p className="text-[11px] text-slate-400 font-mono">
            3-Tier IoT • Bayesian Fusion • OR-Tools CVRPTW
          </p>
        </div>
      </div>

      {/* Real-time KPI Counters */}
      <div className="hidden lg:flex items-center space-x-6">
        {/* Tracked H3 Hexagons */}
        <div className="flex items-center space-x-3 border-r border-slate-800 pr-6">
          <div className="text-right">
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-tight">
              Tracked H3 Cells
            </span>
            <div className="flex items-center space-x-2">
              <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-red-950/60 border border-red-500/40 text-red-400 font-semibold">
                {confirmedCount} Confirmed
              </span>
              <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-amber-950/60 border border-amber-500/40 text-amber-400 font-semibold">
                {anomalyCount} SAR
              </span>
            </div>
          </div>
        </div>

        {/* Estimated Polymer Mass */}
        <div className="flex items-center space-x-2.5 border-r border-slate-800 pr-6">
          <div className="w-8 h-8 rounded bg-red-950/40 border border-red-500/30 flex items-center justify-center text-red-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-tight">
              Floating Polymer Mass
            </span>
            <span className="font-mono text-sm font-bold text-slate-100">
              {totalMassTons} <span className="text-xs text-red-400">Metric Tons</span>
            </span>
          </div>
        </div>

        {/* Fleet Interception Assets */}
        <div className="flex items-center space-x-2.5 border-r border-slate-800 pr-6">
          <div className="w-8 h-8 rounded bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Anchor className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-tight">
              Active Ships
            </span>
            <span className="font-mono text-sm font-bold text-slate-100">
              {activeVesselsCount} <span className="text-xs text-cyan-400">Deployed</span>
            </span>
          </div>
        </div>

        {/* Ocean Current Assist Fuel Savings */}
        <div className="flex items-center space-x-2.5 border-r border-slate-800 pr-6">
          <div className="w-8 h-8 rounded bg-emerald-950/40 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Flame className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-tight">
              Current-Assist Fuel Saved
            </span>
            <span className="font-mono text-sm font-bold text-emerald-400">
              +{fuelSavedLiters.toLocaleString()} L <span className="text-[10px] text-emerald-500/80">(+18.5% Boost)</span>
            </span>
          </div>
        </div>

        {/* SSE Cloud Stream Pulse */}
        <div className="flex items-center space-x-2">
          <div className="relative flex items-center justify-center w-3 h-3">
            {sseConnected ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </>
            ) : (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
            )}
          </div>
          <div className="text-left font-mono">
            <span className="text-[10px] uppercase text-slate-400 block leading-none">
              Kafka Stream
            </span>
            <span className="text-[10px] text-slate-300">
              {sseConnected ? `${sseEventCount} msgs rx` : 'Reconnecting...'}
            </span>
          </div>
        </div>
      </div>

      {/* Tactical Instant Role Switcher Toggle */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center p-0.5 rounded-lg bg-slate-900 border border-cyan-500/30">
          <button
            onClick={() => onRoleChange('FLEET_ADMIN')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              role === 'FLEET_ADMIN'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-[0_0_10px_rgba(0,240,255,0.2)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            <span>Commander HUD</span>
          </button>
          <button
            onClick={() => onRoleChange('VESSEL_CAPTAIN')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
              role === 'VESSEL_CAPTAIN'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/40 shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>Captain Bridge</span>
          </button>
        </div>
      </div>
    </header>
  );
};

