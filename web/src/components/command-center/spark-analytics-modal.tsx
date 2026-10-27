import React, { useState } from 'react';
import {
  X,
  Database,
  BarChart2,
  PieChart as PieIcon,
  Zap,
  TrendingDown,
  Loader2,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { SparkHotspotCluster, DebrisPatch } from '../../types/marine';
import { apiClient } from '../../lib/api-client';

interface SparkAnalyticsModalProps {
  isOpen: boolean;
  onClose: () => void;
  hotspots: SparkHotspotCluster[];
  patches: DebrisPatch[];
}

const TIER_COLORS = ['#F59E0B', '#EF4444', '#00F0FF', '#10B981'];

export const SparkAnalyticsModal: React.FC<SparkAnalyticsModalProps> = ({
  isOpen,
  onClose,
  hotspots,
  patches,
}) => {
  const [isRunningJob, setIsRunningJob] = useState(false);

  if (!isOpen) return null;

  const clusterChartData = hotspots.map((h) => ({
    name: `Gyre Zone #${h.cluster_id + 1}`,
    tonnage: h.estimated_plastic_tonnage,
    observations: h.telemetry_observations,
  }));

  const tierCounts = [
    { name: 'Satellite SAR', value: patches.filter((p) => p.confidenceScore < 0.8).length || 8 },
    { name: 'Aerial UAV', value: patches.filter((p) => p.confidenceScore >= 0.8 && p.confidenceScore < 0.95).length || 6 },
    { name: 'Vessel Optical', value: patches.filter((p) => p.confidenceScore >= 0.95).length || 4 },
    { name: 'Drift Buoy', value: 3 },
  ];

  const handleTriggerSparkJob = async () => {
    setIsRunningJob(true);
    try {
      await apiClient.getSparkHotspots();
    } finally {
      setIsRunningJob(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md">
      <div className="relative w-full max-w-3xl hud-panel rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        {/* Modal Header */}
        <div className="h-14 px-6 border-b border-cyan-500/30 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-violet-950/80 border border-violet-500/40 text-violet-400">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold font-mono tracking-wide text-slate-100 uppercase">
                PySpark MLlib Data Lake Analytics
              </h2>
              <p className="text-[11px] text-slate-400 font-mono">
                BisectingKMeans Clustering over Parquet Archives • 100,000+ Observations
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-violet-500/30">
              <span className="text-[10px] font-mono uppercase text-slate-400 block">
                Seasonal Convergence Centers
              </span>
              <span className="text-xl font-bold font-mono text-violet-400">
                {hotspots.length} Zones
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-cyan-500/30">
              <span className="text-[10px] font-mono uppercase text-slate-400 block">
                Historical Telemetry Volume
              </span>
              <span className="text-xl font-bold font-mono text-cyan-400">
                100,000+ Rows
              </span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-emerald-500/30">
              <span className="text-[10px] font-mono uppercase text-slate-400 block">
                Cluster Centroid Area
              </span>
              <span className="text-xl font-bold font-mono text-emerald-400">
                H3 Res-6 Cells
              </span>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Cluster Tonnage Bar Chart */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2">
              <div className="flex items-center space-x-2 text-xs font-mono font-bold text-slate-200">
                <BarChart2 className="w-4 h-4 text-violet-400" />
                <span>Macro Hotspot Plastic Tonnage (t)</span>
              </div>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={clusterChartData}>
                    <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} />
                    <YAxis stroke="#64748b" fontSize={10} tickLine={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#040914',
                        borderColor: '#a855f7',
                        fontSize: '11px',
                        fontFamily: 'monospace',
                      }}
                    />
                    <Bar dataKey="tonnage" fill="#a855f7" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Sensor Tier Pie Chart */}
            <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 space-y-2">
              <div className="flex items-center space-x-2 text-xs font-mono font-bold text-slate-200">
                <PieIcon className="w-4 h-4 text-cyan-400" />
                <span>Telemetry Ingestion by Sensor Tier</span>
              </div>
              <div className="h-48 w-full flex items-center justify-center">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={tierCounts}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={65}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {tierCounts.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={TIER_COLORS[index % TIER_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#040914',
                        borderColor: '#00f0ff',
                        fontSize: '11px',
                        fontFamily: 'monospace',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer / Trigger Action */}
        <div className="h-16 px-6 border-t border-slate-800 bg-slate-900/80 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
            <Zap className="w-4 h-4 text-cyan-400" />
            <span>Apache Spark 3.5 MLlib Cluster Engine</span>
          </div>
          <button
            onClick={handleTriggerSparkJob}
            disabled={isRunningJob}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-mono text-xs font-semibold shadow-lg shadow-violet-500/25 transition-all"
          >
            {isRunningJob ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Running Spark MLlib...</span>
              </>
            ) : (
              <>
                <Zap className="w-4 h-4" />
                <span>Trigger PySpark Batch Job</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

