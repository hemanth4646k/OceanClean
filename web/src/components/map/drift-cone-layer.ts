import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { H3HexagonLayer } from '@deck.gl/geo-layers';
import { latLngToCell } from 'h3-js';
import { DebrisPatch } from '../../types/marine';

interface DriftConeLayerProps {
  patches: DebrisPatch[];
  selectedPatchId?: string | null;
}

export function createDriftConeLayers({ patches, selectedPatchId }: DriftConeLayerProps) {
  // Focus on confirmed patches or selected patch
  const targetPatches = selectedPatchId
    ? patches.filter((p) => p.id === selectedPatchId)
    : patches.filter((p) => p.confidenceScore >= 0.8).slice(0, 8);

  const pathData: any[] = [];
  const uncertaintyRings: any[] = [];
  const ghostHexagons: any[] = [];

  for (const p of targetPatches) {
    const lat0 = p.latitude;
    const lon0 = p.longitude;

    const dLon6h = p.predictedLon6h !== undefined ? (p.predictedLon6h - lon0) : 0.35;
    const dLat6h = p.predictedLat6h !== undefined ? (p.predictedLat6h - lat0) : 0.0;

    const pt0 = [lon0, lat0];
    const pt6 = [lon0 + dLon6h, lat0 + dLat6h];
    const pt12 = [lon0 + dLon6h * 2.0, lat0 + dLat6h * 2.0];
    const pt24 = [lon0 + dLon6h * 4.0, lat0 + dLat6h * 4.0];

    pathData.push({
      id: p.id,
      path: [pt0, pt6, pt12, pt24],
    });

    // Uncertainty rings at 6h (5 km = 5000m), 12h (12 km), 24h (25 km)
    uncertaintyRings.push(
      { position: pt6, radius: 5000, horizon: '6h', color: [0, 240, 255, 60] },
      { position: pt12, radius: 12000, horizon: '12h', color: [245, 158, 11, 40] },
      { position: pt24, radius: 25000, horizon: '24h', color: [239, 68, 68, 30] },
    );

    // Ghost H3 hexagon at T+24h
    try {
      const ghostH3 = latLngToCell(pt24[1], pt24[0], 7);
      ghostHexagons.push({ h3Index: ghostH3, patchId: p.id });
    } catch {
      // ignore boundary errors
    }
  }

  const paths = new PathLayer({
    id: 'drift-paths-layer',
    data: pathData,
    pickable: false,
    widthMinPixels: 2,
    getPath: (d: any) => d.path,
    getColor: [0, 240, 255, 180],
    dashJustified: true,
  });

  const rings = new ScatterplotLayer({
    id: 'drift-uncertainty-rings',
    data: uncertaintyRings,
    pickable: false,
    stroked: true,
    filled: true,
    lineWidthMinPixels: 1,
    getPosition: (d: any) => d.position,
    getRadius: (d: any) => d.radius,
    getFillColor: (d: any) => d.color,
    getLineColor: (d: any) => [d.color[0], d.color[1], d.color[2], 180],
  });

  const ghosts = new H3HexagonLayer({
    id: 'drift-ghost-hexagons',
    data: ghostHexagons,
    pickable: false,
    wireframe: true,
    filled: false,
    extruded: false,
    getHexagon: (d: any) => d.h3Index,
    getLineColor: [0, 240, 255, 140],
    lineWidthMinPixels: 1.5,
  });

  return [paths, rings, ghosts];
}

