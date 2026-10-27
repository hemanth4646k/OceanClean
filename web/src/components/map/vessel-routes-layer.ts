import { PathLayer, ScatterplotLayer, IconLayer } from '@deck.gl/layers';
import { Vessel, InterceptionRoute } from '../../types/marine';

interface VesselRoutesLayerProps {
  vessels: Vessel[];
  routes: InterceptionRoute[];
  selectedVesselId?: string | null;
  onVesselClick?: (vessel: Vessel) => void;
}

export function createVesselRoutesLayers({
  vessels,
  routes,
  selectedVesselId,
  onVesselClick,
}: VesselRoutesLayerProps) {
  // 1. Build route paths
  const routePaths: any[] = [];
  const waypointsData: any[] = [];

  for (const r of routes) {
    const vessel = vessels.find((v) => v.id === r.vesselId);
    if (!vessel || !r.waypointsJson || r.waypointsJson.length === 0) continue;

    const pathPoints: [number, number][] = [[vessel.longitude, vessel.latitude]];
    for (const wp of r.waypointsJson) {
      pathPoints.push([wp.targetLongitude, wp.targetLatitude]);
      waypointsData.push({
        position: [wp.targetLongitude, wp.targetLatitude],
        h3Index: wp.h3Index,
        completed: wp.completed,
        vesselName: vessel.name,
      });
    }

    routePaths.push({
      id: r.id,
      vesselId: r.vesselId,
      path: pathPoints,
      isSelected: r.vesselId === selectedVesselId,
    });
  }

  const paths = new PathLayer({
    id: 'vessel-routes-paths',
    data: routePaths,
    pickable: false,
    widthMinPixels: 3,
    getPath: (d: any) => d.path,
    getColor: (d: any) => (d.isSelected ? [0, 240, 255, 230] : [16, 185, 129, 210]),
  });

  const waypointDots = new ScatterplotLayer({
    id: 'vessel-waypoint-markers',
    data: waypointsData,
    pickable: true,
    stroked: true,
    filled: true,
    radiusMinPixels: 4,
    radiusMaxPixels: 8,
    getPosition: (d: any) => d.position,
    getFillColor: (d: any) => (d.completed ? [16, 185, 129, 250] : [0, 240, 255, 220]),
    getLineColor: [255, 255, 255, 200],
    lineWidthMinPixels: 1.5,
  });

  // 2. Vessel Markers
  const vesselMarkers = new ScatterplotLayer({
    id: 'vessel-ship-markers',
    data: vessels,
    pickable: true,
    stroked: true,
    filled: true,
    radiusMinPixels: 7,
    radiusMaxPixels: 14,
    getPosition: (v: Vessel) => [v.longitude, v.latitude],
    getFillColor: (v: Vessel) => {
      if (v.id === selectedVesselId) return [0, 240, 255, 255];
      if (v.status === 'HARVESTING') return [16, 185, 129, 240];
      if (v.status === 'EN_ROUTE') return [0, 240, 255, 220];
      return [148, 163, 184, 220];
    },
    getLineColor: [255, 255, 255, 240],
    lineWidthMinPixels: 2,
    onClick: (info: any) => {
      if (info.object && onVesselClick) {
        onVesselClick(info.object);
      }
    },
  });

  return [paths, waypointDots, vesselMarkers];
}

