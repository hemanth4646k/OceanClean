import React, { useState } from 'react';
import { Terminal, ChevronUp, ChevronDown, Trash2 } from 'lucide-react';
import { SsePipelineEvent } from '../../types/marine';

interface LiveCloudTerminalProps {
  events: SsePipelineEvent[];
  onClear: () => void;
  isConnected: boolean;
}

export const LiveCloudTerminal: React.FC<LiveCloudTerminalProps> = ({
  events,
  onClear,
  isConnected,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState<string>('ALL');

  const filteredEvents = events.filter((e) => {
    if (filter === 'ALL') return true;
    if (filter === 'KAFKA' && e.stage === 'KAFKA_INGEST') return true;
    if (filter === 'BAYESIAN' && e.stage === 'BAYESIAN_FUSION') return true;
    if (filter === 'OPEN-METEO' && e.stage === 'OPEN_METEO_DRIFT') return true;
    if (filter === 'SPARK' && e.stage === 'SPARK_BATCH') return true;
    if (filter === 'OR-TOOLS' && e.stage === 'ORTOOLS_ROUTE') return true;
    return false;
  });

  return (
    <div
      className={`fixed left-4 bottom-6 z-30 transition-all duration-300 ${
        isOpen ? 'w-[440px] h-64' : 'w-56 h-10'
      } hud-panel rounded-2xl overflow-hidden shadow-2xl flex flex-col`}
    >
      {/* Terminal Titlebar */}
      <div className="h-10 px-3 bg-slate-900/90 border-b border-cyan-500/30 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center space-x-2">
          <Terminal className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-200">Cloud Event Stream</span>
          <span
            className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-emerald-400' : 'bg-amber-400'
            }`}
          />
        </div>
        <div className="flex items-center space-x-1">
          {isOpen && (
            <button
              onClick={onClear}
              className="p-1 rounded text-slate-400 hover:text-red-400"
              title="Clear Terminal Logs"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="p-1 rounded text-slate-400 hover:text-cyan-400"
          >
            {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Expanded Terminal Body */}
      {isOpen && (
        <div className="flex-1 flex flex-col p-2 bg-slate-950/90 text-xs font-mono overflow-hidden">
          {/* Filters */}
          <div className="flex items-center space-x-1 pb-2 border-b border-slate-800 text-[10px] overflow-x-auto">
            {['ALL', 'KAFKA', 'BAYESIAN', 'OPEN-METEO', 'OR-TOOLS'].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-1.5 py-0.5 rounded transition-all ${
                  filter === f
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/40'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Logs scroll container */}
          <div className="flex-1 overflow-y-auto space-y-1.5 pt-2 pr-1">
            {filteredEvents.length === 0 ? (
              <p className="text-[11px] text-slate-500 italic p-2 text-center">
                Listening to Kafka, Bayesian fusion & OR-Tools dispatch...
              </p>
            ) : (
              filteredEvents.map((e, idx) => (
                <div key={idx} className="leading-tight text-[11px] flex items-start space-x-1.5">
                  <span className="text-slate-500 shrink-0">
                    {e.timestamp ? e.timestamp.slice(11, 19) : '00:00:00'}
                  </span>
                  <span
                    className={`px-1 rounded text-[9px] font-bold shrink-0 ${
                      e.stage === 'KAFKA_INGEST'
                        ? 'bg-amber-950 text-amber-400 border border-amber-500/30'
                        : e.stage === 'BAYESIAN_FUSION'
                        ? 'bg-red-950 text-red-400 border border-red-500/30'
                        : e.stage === 'ORTOOLS_ROUTE'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30'
                        : 'bg-cyan-950 text-cyan-400 border border-cyan-500/30'
                    }`}
                  >
                    {e.stage}
                  </span>
                  <span className="text-slate-300 break-words">{e.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

