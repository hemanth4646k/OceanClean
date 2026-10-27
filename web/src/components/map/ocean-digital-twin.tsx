import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import Map from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

import {
  DebrisPatch,
  Vessel,
  InterceptionRoute,
  CurrentGridPoint,
  SparkHotspotCluster,
  LayerVisibilityState,
} from '../../types/marine';
import { createH3DebrisLayer } from './h3-debris-layer';
import { createDriftConeLayers } from './drift-cone-layer';
import { createVesselRoutesLayers } from './vessel-routes-layer';
import { createSparkHotspotsLayers } from './spark-hotspots-layer';

const CARTO_DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

interface OceanDigitalTwinProps {
  patches: DebrisPatch[];
  vessels: Vessel[];
  routes: InterceptionRoute[];
  currentsGrid: CurrentGridPoint[];
  sparkHotspots: SparkHotspotCluster[];
  layers: LayerVisibilityState;
  selectedPatchId: string | null;
  selectedVesselId: string | null;
  onSelectPatch: (patch: DebrisPatch | null) => void;
  onSelectVessel: (vessel: Vessel | null) => void;
}

const INITIAL_VIEW_STATE = {
  latitude: 31.5,
  longitude: -145.0,
  zoom: 5.2,
  pitch: 42,
  bearing: -8,
  maxPitch: 65,
  minZoom: 3,
  maxZoom: 14,
};

export const OceanDigitalTwin: React.FC<OceanDigitalTwinProps> = ({
  patches,
  vessels,
  routes,
  currentsGrid,
  sparkHotspots,
  layers,
  selectedPatchId,
  selectedVesselId,
  onSelectPatch,
  onSelectVessel,
}) => {
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [hoverInfo, setHoverInfo] = useState<any>(null);
  const particleCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Sync 2D / 3D Pitch toggle from dock
  useEffect(() => {
    setViewState((prev) => ({
      ...prev,
      pitch: layers.pitch3D ? 45 : 0,
    }));
  }, [layers.pitch3D]);

  // Focus camera when vessel or patch is selected
  useEffect(() => {
    if (selectedVesselId) {
      const v = vessels.find((item) => item.id === selectedVesselId);
      if (v) {
        setViewState((prev) => ({
          ...prev,
          latitude: v.latitude,
          longitude: v.longitude,
          zoom: Math.max(prev.zoom, 6.5),
        }));
      }
    }
  }, [selectedVesselId, vessels]);

  useEffect(() => {
    if (selectedPatchId) {
      const p = patches.find((item) => item.id === selectedPatchId);
      if (p) {
        setViewState((prev) => ({
          ...prev,
          latitude: p.latitude,
          longitude: p.longitude,
          zoom: Math.max(prev.zoom, 6.2),
        }));
      }
    }
  }, [selectedPatchId, patches]);

  // Animated Ocean Currents Particle System
  useEffect(() => {
    if (!layers.currentParticles || !particleCanvasRef.current) return;
    const canvas = particleCanvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    const numParticles = 1200;

    const particles: Array<{
      x: number;
      y: number;
      age: number;
      maxAge: number;
      u: number;
      v: number;
      isStorm: boolean;
    }> = [];

    const width = (canvas.width = window.innerWidth);
    const height = (canvas.height = window.innerHeight);

    // Seed particles
    for (let i = 0; i < numParticles; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        age: Math.floor(Math.random() * 80),
        maxAge: 70 + Math.random() * 50,
        u: 0.8 + Math.random() * 0.4,
        v: (Math.random() - 0.4) * 0.3,
        isStorm: Math.random() < 0.12,
      });
    }

    const render = () => {
      ctx.fillStyle = 'rgba(4, 9, 20, 0.08)';
      ctx.fillRect(0, 0, width, height);

      for (const p of particles) {
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);

        p.x += p.u * 1.5;
        p.y += p.v * 1.5;
        p.age++;

        ctx.lineTo(p.x, p.y);
        ctx.strokeStyle = p.isStorm
          ? 'rgba(168, 85, 247, 0.65)'
          : 'rgba(0, 240, 255, 0.6)';
        ctx.lineWidth = p.isStorm ? 1.5 : 1.0;
        ctx.stroke();

        if (p.age >= p.maxAge || p.x > width || p.x < 0 || p.y > height || p.y < 0) {
          p.x = Math.random() * width;
          p.y = Math.random() * height;
          p.age = 0;
        }
      }

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      if (ctx) ctx.clearRect(0, 0, width, height);
    };
  }, [layers.currentParticles]);

  // Deck.gl Layers
  const deckLayers = useMemo(() => {
    const list: any[] = [];

    // 1. Spark Hotspots
    if (layers.sparkHotspots && sparkHotspots.length > 0) {
      list.push(...createSparkHotspotsLayers({
        hotspots: sparkHotspots,
        onHover: (info) => setHoverInfo(info?.object ? { type: 'spark', object: info.object, x: info.x, y: info.y } : null),
      }));
    }

    // 2. Lagrangian Drift Cones
    if (layers.driftCones && patches.length > 0) {
      list.push(...createDriftConeLayers({
        patches,
        selectedPatchId,
      }));
    }

    // 3. Vessel Interception Routes
    if (layers.vesselRoutes && vessels.length > 0) {
      list.push(...createVesselRoutesLayers({
        vessels,
        routes,
        selectedVesselId,
        onVesselClick: (v) => onSelectVessel(v),
      }));
    }

    // 4. 3D H3 Debris Hexagons
    if (layers.h3Debris && patches.length > 0) {
      list.push(createH3DebrisLayer({
        patches,
        selectedPatchId,
        onHover: (info) => {
          if (info.object) {
            setHoverInfo({ type: 'patch', object: info.object, x: info.x, y: info.y });
          } else if (!hoverInfo || hoverInfo.type === 'patch') {
            setHoverInfo(null);
          }
        },
        onClick: (info) => {
          if (info.object) {
            onSelectPatch(info.object);
          }
        },
      }));
    }

    return list;
  }, [
    layers,
    patches,
    vessels,
    routes,
    sparkHotspots,
    selectedPatchId,
    selectedVesselId,
    onSelectPatch,
    onSelectVessel,
    hoverInfo,
  ]);

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#040914]">
      {/* Deck.gl + MapLibre Master Viewport */}
      <DeckGL
        viewState={viewState as any}
        onViewStateChange={(e: any) => setViewState(e.viewState)}
        controller={true}
        layers={deckLayers}
        getCursor={({ isHovering }) => (isHovering ? 'pointer' : 'default')}
      >
        <Map
          reuseMaps
          mapStyle={CARTO_DARK_STYLE}
          attributionControl={false}
        />
      </DeckGL>

      {/* Synchronized HTML5 Currents Particle Canvas */}
      {layers.currentParticles && (
        <canvas
          ref={particleCanvasRef}
          className="absolute inset-0 pointer-events-none z-10"
        />
      )}

      {/* Tactical Hover Telemetry Card */}
      {hoverInfo && hoverInfo.object && (
        <div
          className="fixed z-50 pointer-events-none transform -translate-x-1/2 -translate-y-full mb-3"
          style={{ left: hoverInfo.x, top: hoverInfo.y }}
        >
          {hoverInfo.type === 'patch' && (
            <div className="hud-panel p-3 rounded-lg min-w-[220px] text-xs font-mono space-y-1">
              <div className="flex items-center justify-between border-b border-cyan-500/30 pb-1">
                <span className="text-cyan-400 font-bold uppercase">
                  H3 Cell {hoverInfo.object.h3Index.slice(0, 9)}...
                </span>
                <span
                  className={`px-1 py-0.5 rounded text-[10px] font-bold ${
                    hoverInfo.object.confidenceScore >= 0.8
                      ? 'bg-red-950 text-red-400 border border-red-500/40'
                      : 'bg-amber-950 text-amber-400 border border-amber-500/40'
                  }`}
                >
                  {hoverInfo.object.status}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Bayesian Conf:</span>
                <span className="text-slate-100 font-bold">
                  {(hoverInfo.object.confidenceScore * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Est. Plastic Mass:</span>
                <span className="text-red-400 font-bold">
                  {(hoverInfo.object.estimatedMassKg / 1000).toFixed(2)} Metric Tons
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Polymer Density:</span>
                <span className="text-slate-200">
                  {hoverInfo.object.polymerDensityKgKm2.toFixed(1)} kg/km²
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Coordinates:</span>
                <span className="text-slate-300">
                  {hoverInfo.object.latitude.toFixed(2)}°N, {Math.abs(hoverInfo.object.longitude).toFixed(2)}°W
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Ocean Current:</span>
                <span className="text-cyan-400">
                  {hoverInfo.object.currentVelocityMs || 1.2} m/s @ {hoverInfo.object.currentDirectionDeg || 90}°
                </span>
              </div>
            </div>
          )}

          {hoverInfo.type === 'spark' && (
            <div className="hud-panel p-3 rounded-lg min-w-[240px] text-xs font-mono space-y-1 border-violet-500/40">
              <div className="flex items-center justify-between border-b border-violet-500/30 pb-1">
                <span className="text-violet-400 font-bold uppercase">
                  Spark Gyre Hotspot #{hoverInfo.object.cluster_id + 1}
                </span>
                <span className="px-1 py-0.5 rounded text-[10px] bg-violet-950 text-violet-300 border border-violet-500/40">
                  MLlib BisectingKMeans
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Est. Plastic Tonnage:</span>
                <span className="text-violet-300 font-bold">
                  {hoverInfo.object.estimated_plastic_tonnage} Metric Tons
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Telemetry Pings:</span>
                <span className="text-slate-200">{hoverInfo.object.telemetry_observations} hits</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Centroid:</span>
                <span className="text-slate-300">
                  {hoverInfo.object.center_latitude.toFixed(2)}°N, {Math.abs(hoverInfo.object.center_longitude).toFixed(2)}°W
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
