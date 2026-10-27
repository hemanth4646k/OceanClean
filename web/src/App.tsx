import React, { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './lib/api-client';
import { useSseTelemetry } from './lib/use-sse-telemetry';
import {
  DebrisPatch,
  Vessel,
  UserRole,
  LayerVisibilityState,
} from './types/marine';
import { TopTelemetryRibbon } from './components/layout/top-telemetry-ribbon';
import { LayerToggleDock } from './components/layout/layer-toggle-dock';
import { OceanDigitalTwin } from './components/map/ocean-digital-twin';
import { SimulationConsole } from './components/command-center/simulation-console';
import { TimeScrubberBar } from './components/command-center/time-scrubber-bar';
import { LiveCloudTerminal } from './components/command-center/live-cloud-terminal';
import { SparkAnalyticsModal } from './components/command-center/spark-analytics-modal';
import { CaptainBridgeView } from './components/vessel-helm/captain-bridge-view';
import {
  interpolatePatchPosition,
  interpolateVesselPosition,
} from './lib/drift-interpolator';

export function App() {
  const queryClient = useQueryClient();
  const [role, setRole] = useState<UserRole>('FLEET_ADMIN');
  const [simulationHour, setSimulationHour] = useState<number>(0);
  const [isSparkModalOpen, setIsSparkModalOpen] = useState(false);

  const [selectedPatch, setSelectedPatch] = useState<DebrisPatch | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);

  const [layers, setLayers] = useState<LayerVisibilityState>({
    h3Debris: true,
    currentParticles: true,
    driftCones: true,
    vesselRoutes: true,
    sparkHotspots: true,
    stormHazard: true,
    pitch3D: true,
  });

  // SSE Real-Time Telemetry Hook
  const { events: sseEvents, isConnected: sseConnected, eventCount: sseCount, clearLogs } =
    useSseTelemetry();

  // Queries
  const { data: rawPatches = [] } = useQuery({
    queryKey: ['debris-patches'],
    queryFn: () => apiClient.getPatches(),
    refetchInterval: 10000,
  });

  const { data: rawVessels = [] } = useQuery({
    queryKey: ['vessels'],
    queryFn: () => apiClient.getVessels(),
    refetchInterval: 10000,
  });

  const { data: routes = [] } = useQuery({
    queryKey: ['trajectories'],
    queryFn: () => apiClient.getRoutes(),
    refetchInterval: 10000,
  });

  const { data: currentsGridData } = useQuery({
    queryKey: ['currents-grid'],
    queryFn: () => apiClient.getCurrentsGrid(),
    staleTime: 60000,
  });

  const { data: sparkHotspotsData } = useQuery({
    queryKey: ['spark-hotspots'],
    queryFn: () => apiClient.getSparkHotspots(),
    staleTime: 60000,
  });

  const currentsGrid = currentsGridData?.grid_points || [];
  const sparkHotspots = sparkHotspotsData?.hotspots || [];

  // Interpolate positions across T+0h to T+24h time-scrubber slider
  const displayedPatches = useMemo(() => {
    if (simulationHour === 0) return rawPatches;
    return rawPatches.map((p) => {
      const pos = interpolatePatchPosition(p, simulationHour);
      return {
        ...p,
        latitude: pos.lat,
        longitude: pos.lon,
        h3Index: pos.h3,
      };
    });
  }, [rawPatches, simulationHour]);

  const displayedVessels = useMemo(() => {
    if (simulationHour === 0) return rawVessels;
    return rawVessels.map((v) => {
      const route = routes.find((r) => r.vesselId === v.id);
      const pos = interpolateVesselPosition(v, route, simulationHour);
      return {
        ...v,
        latitude: pos.lat,
        longitude: pos.lon,
      };
    });
  }, [rawVessels, routes, simulationHour]);

  const handleRefreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['debris-patches'] });
    queryClient.invalidateQueries({ queryKey: ['vessels'] });
    queryClient.invalidateQueries({ queryKey: ['trajectories'] });
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#040914]">
      {/* 1. Top Telemetry Ribbon & Role Switcher */}
      <TopTelemetryRibbon
        patches={displayedPatches}
        vessels={displayedVessels}
        routes={routes}
        role={role}
        onRoleChange={(newRole) => {
          setRole(newRole);
          if (newRole === 'VESSEL_CAPTAIN' && displayedVessels.length > 0) {
            setSelectedVessel(displayedVessels[0]);
          }
        }}
        sseConnected={sseConnected}
        sseEventCount={sseCount}
      />

      {/* 2. 3D WebGL Ocean Digital Twin */}
      <OceanDigitalTwin
        patches={displayedPatches}
        vessels={displayedVessels}
        routes={routes}
        currentsGrid={currentsGrid}
        sparkHotspots={sparkHotspots}
        layers={layers}
        selectedPatchId={selectedPatch?.id || null}
        selectedVesselId={selectedVessel?.id || null}
        onSelectPatch={(patch) => setSelectedPatch(patch)}
        onSelectVessel={(vessel) => {
          setSelectedVessel(vessel);
          if (vessel) setRole('VESSEL_CAPTAIN');
        }}
      />

      {/* 3. Commander Mode: Space-to-Sea Simulation Console */}
      {role === 'FLEET_ADMIN' && (
        <SimulationConsole onScenarioTriggered={handleRefreshAll} />
      )}

      {/* 4. Captain Mode: Vessel Tactical Bridge Helm */}
      {role === 'VESSEL_CAPTAIN' && (
        <CaptainBridgeView
          vessels={displayedVessels}
          selectedVessel={selectedVessel}
          onSelectVessel={(v) => setSelectedVessel(v)}
          routes={routes}
          onWaypointCompleted={handleRefreshAll}
          currentsGrid={currentsGrid}
        />
      )}

      {/* 5. 24-Hour Time-Scrubber Timeline Bar */}
      <TimeScrubberBar
        currentHour={simulationHour}
        onHourChange={(hr) => setSimulationHour(hr)}
      />

      {/* 6. Live Cloud Event Terminal (SSE) */}
      <LiveCloudTerminal
        events={sseEvents}
        onClear={clearLogs}
        isConnected={sseConnected}
      />

      {/* 7. Layer Visibility Dock */}
      <LayerToggleDock
        layers={layers}
        onChange={(newLayers) => setLayers(newLayers)}
      />

      {/* 8. PySpark Big Data Analytics Modal */}
      <SparkAnalyticsModal
        isOpen={isSparkModalOpen}
        onClose={() => setIsSparkModalOpen(false)}
        hotspots={sparkHotspots}
        patches={rawPatches}
      />
    </div>
  );
}

export default App;

