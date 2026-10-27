import React from 'react';
import {
  Box,
  Compass,
  Hexagon,
  Layers,
  Navigation,
  Wind,
  Zap,
} from 'lucide-react';
import { LayerVisibilityState } from '../../types/marine';

interface LayerToggleDockProps {
  layers: LayerVisibilityState;
  onChange: (layers: LayerVisibilityState) => void;
}

export const LayerToggleDock: React.FC<LayerToggleDockProps> = ({ layers, onChange }) => {
  const toggle = (key: keyof LayerVisibilityState) => {
    onChange({
      ...layers,
      [key]: !layers[key],
    });
  };

  return (
    <div className="fixed bottom-6 right-6 z-30 flex items-center space-x-1.5 p-1.5 rounded-xl hud-panel">
      <div className="px-2 py-1 flex items-center space-x-1.5 border-r border-slate-800 text-[11px] font-mono text-cyan-400">
        <Layers className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">LAYERS</span>
      </div>

      {/* 3D H3 Hexagons */}
      <button
        onClick={() => toggle('h3Debris')}
        title="Toggle 3D H3 Debris Hexagons"
        className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all ${
          layers.h3Debris
            ? 'bg-red-500/20 text-red-300 border border-red-500/40 shadow-[0_0_8px_rgba(239,68,68,0.2)]'
            : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        <Hexagon className="w-3.5 h-3.5" />
        <span className="hidden md:inline">H3 Plastic</span>
      </button>

      {/* Ocean Current Particles */}
      <button
        onClick={() => toggle('currentParticles')}
        title="Toggle Ocean Current Streamlines"
        className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all ${
          layers.currentParticles
            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
            : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        <Wind className="w-3.5 h-3.5" />
        <span className="hidden md:inline">Currents</span>
      </button>

      {/* Lagrangian Drift Cones */}
      <button
        onClick={() => toggle('driftCones')}
        title="Toggle 6h/12h/24h Lagrangian Drift Cones"
        className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all ${
          layers.driftCones
            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-[0_0_8px_rgba(245,158,11,0.2)]'
            : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        <Compass className="w-3.5 h-3.5" />
        <span className="hidden md:inline">Drift Cones</span>
      </button>

      {/* Vessel Routes */}
      <button
        onClick={() => toggle('vesselRoutes')}
        title="Toggle OR-Tools Vessel Interception Trajectories"
        className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all ${
          layers.vesselRoutes
            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-[0_0_8px_rgba(16,185,129,0.2)]'
            : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        <Navigation className="w-3.5 h-3.5" />
        <span className="hidden md:inline">Fleet Routes</span>
      </button>

      {/* Spark MLlib Hotspots */}
      <button
        onClick={() => toggle('sparkHotspots')}
        title="Toggle PySpark MLlib Seasonal Hotspots"
        className={`flex items-center space-x-1 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all ${
          layers.sparkHotspots
            ? 'bg-violet-500/20 text-violet-300 border border-violet-500/40 shadow-[0_0_8px_rgba(168,85,247,0.2)]'
            : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        <Zap className="w-3.5 h-3.5" />
        <span className="hidden md:inline">Spark Gyres</span>
      </button>

      {/* 2D / 3D Pitch Toggle */}
      <div className="pl-1 border-l border-slate-800">
        <button
          onClick={() => toggle('pitch3D')}
          title="Toggle 2D / 3D Map Pitch"
          className={`flex items-center space-x-1 px-2 py-1.5 rounded-lg text-xs font-mono transition-all ${
            layers.pitch3D
              ? 'bg-cyan-500/30 text-cyan-200 border border-cyan-400/50'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Box className="w-3.5 h-3.5" />
          <span>{layers.pitch3D ? '3D' : '2D'}</span>
        </button>
      </div>
    </div>
  );
};

