import { H3HexagonLayer } from '@deck.gl/geo-layers';
import { DebrisPatch } from '../../types/marine';

interface H3DebrisLayerProps {
  patches: DebrisPatch[];
  onHover?: (info: any) => void;
  onClick?: (info: any) => void;
  selectedPatchId?: string | null;
}

export function createH3DebrisLayer({
  patches,
  onHover,
  onClick,
  selectedPatchId,
}: H3DebrisLayerProps) {
  return new H3HexagonLayer({
    id: 'h3-debris-layer',
    data: patches,
    pickable: true,
    wireframe: true,
    filled: true,
    extruded: true,
    elevationScale: 40,
    getHexagon: (d: DebrisPatch) => d.h3Index,
    getElevation: (d: DebrisPatch) => Math.max(10, d.polymerDensityKgKm2 || 15),
    getFillColor: (d: DebrisPatch) => {
      if (d.id === selectedPatchId) {
        return [0, 240, 255, 240]; // Selected: Bioluminescent Cyan
      }
      if (d.status === 'CLEARED') {
        return [71, 85, 105, 80]; // Cleared: Slate
      }
      if (d.status === 'INTERCEPT_ASSIGNED') {
        return [16, 185, 129, 210]; // Intercept Assigned: Emerald
      }
      if (d.confidenceScore >= 0.8 || d.status === 'CONFIRMED_PATCH') {
        return [239, 68, 68, 220]; // Confirmed: Coral Crimson
      }
      return [245, 158, 11, 160]; // Unverified SAR anomaly: Radar Amber
    },
    getLineColor: [0, 240, 255, 90],
    lineWidthMinPixels: 1,
    onHover,
    onClick,
    updateTriggers: {
      getFillColor: [selectedPatchId, patches],
      getElevation: [patches],
    },
  });
}

