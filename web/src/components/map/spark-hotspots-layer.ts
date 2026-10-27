import { ScatterplotLayer } from '@deck.gl/layers';
import { H3HexagonLayer } from '@deck.gl/geo-layers';
import { SparkHotspotCluster } from '../../types/marine';

interface SparkHotspotsLayerProps {
  hotspots: SparkHotspotCluster[];
  onHover?: (info: any) => void;
}

export function createSparkHotspotsLayers({ hotspots, onHover }: SparkHotspotsLayerProps) {
  // 1. Res-6 H3 Hexagons for the macro clusters
  const macroHexagons = new H3HexagonLayer({
    id: 'spark-macro-hexagons',
    data: hotspots,
    pickable: true,
    wireframe: true,
    filled: true,
    extruded: true,
    elevationScale: 50,
    getHexagon: (d: SparkHotspotCluster) => d.h3_index_res6,
    getElevation: (d: SparkHotspotCluster) => Math.max(10, d.estimated_plastic_tonnage * 2),
    getFillColor: [168, 85, 247, 130], // Storm Violet
    getLineColor: [168, 85, 247, 220],
    lineWidthMinPixels: 2,
    onHover,
  });

  // 2. Convergence field ripple halos around the centroids
  const halos = new ScatterplotLayer({
    id: 'spark-hotspot-halos',
    data: hotspots,
    pickable: false,
    stroked: true,
    filled: true,
    lineWidthMinPixels: 1.5,
    getPosition: (d: SparkHotspotCluster) => [d.center_longitude, d.center_latitude],
    getRadius: (d: SparkHotspotCluster) => Math.max(25000, d.estimated_plastic_tonnage * 300),
    getFillColor: [168, 85, 247, 25],
    getLineColor: [168, 85, 247, 140],
  });

  return [halos, macroHexagons];
}

