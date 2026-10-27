import React, { useEffect, useState } from 'react';
import { Play, Pause, RotateCcw, Clock } from 'lucide-react';

interface TimeScrubberBarProps {
  currentHour: number;
  onHourChange: (hour: number) => void;
}

export const TimeScrubberBar: React.FC<TimeScrubberBarProps> = ({
  currentHour,
  onHourChange,
}) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<1 | 5 | 10>(1);

  useEffect(() => {
    let interval: any = null;
    if (isPlaying) {
      interval = setInterval(() => {
        onHourChange(Math.min(24, currentHour + 0.1 * playbackSpeed));
        if (currentHour >= 24) {
          setIsPlaying(false);
        }
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isPlaying, currentHour, playbackSpeed, onHourChange]);

  const handleReset = () => {
    setIsPlaying(false);
    onHourChange(0);
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 w-[92vw] max-w-2xl px-4 py-2.5 rounded-2xl hud-panel flex items-center space-x-4 shadow-2xl">
      {/* Play/Pause Button */}
      <button
        onClick={() => setIsPlaying(!isPlaying)}
        className="w-9 h-9 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/50 flex items-center justify-center text-cyan-300 transition-colors shadow-[0_0_10px_rgba(0,240,255,0.2)]"
        title={isPlaying ? 'Pause Simulation' : 'Play 24h Lagrangian Drift'}
      >
        {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
      </button>

      {/* Reset to T+0h */}
      <button
        onClick={handleReset}
        className="p-2 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors"
        title="Reset to T+0h"
      >
        <RotateCcw className="w-4 h-4" />
      </button>

      {/* Timeline Horizon Indicator */}
      <div className="flex items-center space-x-1.5 font-mono min-w-[75px]">
        <Clock className="w-3.5 h-3.5 text-cyan-400" />
        <span className="text-xs font-bold text-slate-100">
          T+{currentHour.toFixed(1)}h
        </span>
      </div>

      {/* Slider */}
      <div className="flex-1 relative flex items-center">
        <input
          type="range"
          min="0"
          max="24"
          step="0.1"
          value={currentHour}
          onChange={(e) => onHourChange(parseFloat(e.target.value))}
          className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 focus:outline-none"
        />
        {/* Markers at 6h, 12h, 24h */}
        <div className="absolute -bottom-4 left-0 right-0 flex justify-between text-[9px] font-mono text-slate-500 pointer-events-none">
          <span>0h (Now)</span>
          <span className="text-amber-500/70">6h Drift</span>
          <span className="text-cyan-500/70">12h</span>
          <span className="text-red-500/70">24h Intercept</span>
        </div>
      </div>

      {/* Playback Speed Selector */}
      <div className="flex items-center space-x-1 pl-2 border-l border-slate-800 font-mono text-xs">
        {[1, 5, 10].map((spd) => (
          <button
            key={spd}
            onClick={() => setPlaybackSpeed(spd as 1 | 5 | 10)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold transition-all ${
              playbackSpeed === spd
                ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-400/50'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {spd}x
          </button>
        ))}
      </div>
    </div>
  );
};

