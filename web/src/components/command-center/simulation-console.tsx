import React, { useState } from 'react';
import {
  Satellite,
  Plane,
  UploadCloud,
  CloudLightning,
  Cpu,
  ChevronLeft,
  ChevronRight,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';

interface SimulationConsoleProps {
  onScenarioTriggered: () => void;
}

export const SimulationConsole: React.FC<SimulationConsoleProps> = ({
  onScenarioTriggered,
}) => {
  const [isOpen, setIsOpen] = useState(true);
  const [loadingStep, setLoadingStep] = useState<number | null>(null);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  const handleStep = async (stepNum: number, action: () => Promise<any>) => {
    try {
      setLoadingStep(stepNum);
      await action();
      setCompletedSteps((prev) => new Set(prev).add(stepNum));
      onScenarioTriggered();
    } catch (err: any) {
      console.error(`Simulation step ${stepNum} failed:`, err);
    } finally {
      setLoadingStep(null);
    }
  };

  return (
    <aside
      className={`fixed top-20 left-4 z-30 transition-all duration-300 ${
        isOpen ? 'w-80' : 'w-10'
      }`}
    >
      <div className="relative hud-panel rounded-2xl overflow-hidden shadow-2xl">
        {/* Header / Toggle Button */}
        <div className="h-10 px-3 flex items-center justify-between border-b border-cyan-500/30 bg-slate-900/80">
          {isOpen && (
            <div className="flex items-center space-x-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <h2 className="text-xs font-bold font-mono tracking-wider text-cyan-300 uppercase">
                Space-to-Sea Simulator
              </h2>
            </div>
          )}
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="p-1 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors ml-auto"
            title={isOpen ? 'Collapse Console' : 'Expand Simulation Console'}
          >
            {isOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>

        {/* Console Content */}
        {isOpen && (
          <div className="p-3.5 space-y-3">
            <p className="text-[11px] text-slate-400 leading-relaxed font-sans">
              Drive the end-to-end cloud pipeline through interactive operational stages:
            </p>

            {/* Step 1: Satellite SAR Pass */}
            <button
              onClick={() =>
                handleStep(1, () => apiClient.simulateScenario('SATELLITE_SAR_SWEEP'))
              }
              disabled={loadingStep !== null}
              className={`w-full group p-2.5 rounded-xl border text-left transition-all ${
                completedSteps.has(1)
                  ? 'bg-amber-950/30 border-amber-500/50 text-slate-200'
                  : 'bg-slate-900/60 border-slate-800 hover:border-amber-500/40 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 group-hover:scale-105 transition-transform">
                    <Satellite className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block font-mono text-amber-300">
                      Step 1: Satellite SAR Pass
                    </span>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      12 Anomalies (Conf: 0.55)
                    </span>
                  </div>
                </div>
                {loadingStep === 1 ? (
                  <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
                ) : completedSteps.has(1) ? (
                  <CheckCircle2 className="w-4 h-4 text-amber-400" />
                ) : null}
              </div>
            </button>

            {/* Step 2: Launch UAV Recon */}
            <button
              onClick={() =>
                handleStep(2, () => apiClient.simulateScenario('UAV_RECON_VERIFICATION'))
              }
              disabled={loadingStep !== null}
              className={`w-full group p-2.5 rounded-xl border text-left transition-all ${
                completedSteps.has(2)
                  ? 'bg-red-950/30 border-red-500/50 text-slate-200'
                  : 'bg-slate-900/60 border-slate-800 hover:border-red-500/40 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-red-500/20 text-red-400 group-hover:scale-105 transition-transform">
                    <Plane className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block font-mono text-red-300">
                      Step 2: Launch UAV Recon
                    </span>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      Bayesian Fusion (Conf &ge; 80%)
                    </span>
                  </div>
                </div>
                {loadingStep === 2 ? (
                  <Loader2 className="w-4 h-4 text-red-400 animate-spin" />
                ) : completedSteps.has(2) ? (
                  <CheckCircle2 className="w-4 h-4 text-red-400" />
                ) : null}
              </div>
            </button>

            {/* Step 3: Edge Burst Sync */}
            <button
              onClick={() =>
                handleStep(3, () => apiClient.simulateScenario('EDGE_BURST_SYNC'))
              }
              disabled={loadingStep !== null}
              className={`w-full group p-2.5 rounded-xl border text-left transition-all ${
                completedSteps.has(3)
                  ? 'bg-cyan-950/30 border-cyan-500/50 text-slate-200'
                  : 'bg-slate-900/60 border-slate-800 hover:border-cyan-500/40 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-cyan-500/20 text-cyan-400 group-hover:scale-105 transition-transform">
                    <UploadCloud className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block font-mono text-cyan-300">
                      Step 3: Edge Burst Sync
                    </span>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      35 Reconnected Vessel Hits
                    </span>
                  </div>
                </div>
                {loadingStep === 3 ? (
                  <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                ) : completedSteps.has(3) ? (
                  <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                ) : null}
              </div>
            </button>

            {/* Step 4: Inject Storm Cell */}
            <button
              onClick={() =>
                handleStep(4, () => apiClient.simulateScenario('INJECT_STORM_CELL', 32.5, -144.5))
              }
              disabled={loadingStep !== null}
              className={`w-full group p-2.5 rounded-xl border text-left transition-all ${
                completedSteps.has(4)
                  ? 'bg-violet-950/30 border-violet-500/50 text-slate-200'
                  : 'bg-slate-900/60 border-slate-800 hover:border-violet-500/40 text-slate-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-violet-500/20 text-violet-400 group-hover:scale-105 transition-transform">
                    <CloudLightning className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block font-mono text-violet-300">
                      Step 4: Inject Storm Cell
                    </span>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      5.8m Waves (Storm Penalty)
                    </span>
                  </div>
                </div>
                {loadingStep === 4 ? (
                  <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                ) : completedSteps.has(4) ? (
                  <CheckCircle2 className="w-4 h-4 text-violet-400" />
                ) : null}
              </div>
            </button>

            {/* Step 5: Run OR-Tools Fleet Optimizer */}
            <button
              onClick={() => handleStep(5, () => apiClient.generateRoutes())}
              disabled={loadingStep !== null}
              className={`w-full group p-3 rounded-xl border text-left transition-all ${
                completedSteps.has(5)
                  ? 'bg-emerald-950/40 border-emerald-500/60 text-slate-100 shadow-[0_0_15px_rgba(16,185,129,0.25)]'
                  : 'bg-emerald-950/20 border-emerald-500/40 hover:bg-emerald-950/30 text-emerald-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 group-hover:scale-105 transition-transform">
                    <Cpu className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block font-mono text-emerald-400">
                      Step 5: Run OR-Tools Optimizer
                    </span>
                    <span className="text-[10px] text-slate-400 block font-mono">
                      Current-Assisted Moving Targets
                    </span>
                  </div>
                </div>
                {loadingStep === 5 ? (
                  <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
                ) : completedSteps.has(5) ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : null}
              </div>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

