import type { GeoJsonObject } from 'geojson'
import { useEffect } from 'react'
import { GeoJSON, MapContainer, Pane, Rectangle, useMap } from 'react-leaflet'
import land from '@/assets/ne_110m_land.json'
import type { LiveState } from '@/lib/useLive'
import type { Box, Grid, Hotspots, LatLon, Replay } from '@/lib/types'
import { GraticuleLayer } from './GraticuleLayer'
import { HeatLayer } from './HeatLayer'
import { COLORS } from './colors'
import {
  DraggableTargets,
  GhostLayer,
  HotspotLayer,
  PatchLayer,
  RouteLine,
  VesselLayer,
} from './OverlayLayers'
import { withMoves } from './routes'
import { ParticleLayer } from './ParticleLayer'
import { ReplayLayer } from './ReplayLayer'

export type LayerKey =
  'particles' | 'heatmap' | 'hotspots' | 'wake' | 'patches' | 'ghosts' | 'route'
export type Layers = Record<LayerKey, boolean>

const boxBounds = (b: Box): [LatLon, LatLon] => [
  [b.lat_min, b.lon_min],
  [b.lat_max, b.lon_max],
]

function FitBox({ box }: { box: Box }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(boxBounds(box), { padding: [20, 20] })
  }, [map, box])
  return null
}

export function LiveMap({
  live,
  layers,
  missionBox,
  grid,
  hotspots,
  particleSpeed,
  modify,
  replay,
}: {
  live: LiveState
  layers: Layers
  missionBox: Box | null
  grid: Grid | null
  hotspots: Hotspots | null
  particleSpeed: number
  /** Operator-moved targets of the pending route while modifying it, else null. */
  modify: { moves: Record<string, LatLon>; onMove: (patchId: string, to: LatLon) => void } | null
  /** The time slider: replay parcels at a frame instead of the live overlays, else null. */
  replay: { data: Replay; frame: number } | null
}) {
  const { vessel, routes, patches } = live
  const collected = new Set(patches.filter((p) => p.mass_kg <= 0).map((p) => p.patch_id))
  const targets = new Set(
    [routes.active, routes.pending].flatMap((r) => r?.targets.map((t) => t.patch_id) ?? []),
  )
  const here: LatLon | null = vessel ? [vessel.lat, vessel.lon] : null
  return (
    <MapContainer
      center={[35, -142]}
      zoom={6}
      minZoom={3}
      maxZoom={12}
      zoomControl={false}
      attributionControl={false}
      worldCopyJump={false}
      className="h-full w-full"
    >
      {missionBox && <FitBox box={missionBox} />}
      <GraticuleLayer />
      <Pane name="land" style={{ zIndex: 320 }}>
        <GeoJSON
          data={land as GeoJsonObject}
          style={{ color: '#2b3b4f', weight: 1, fillColor: '#16212e', fillOpacity: 1 }}
          interactive={false}
        />
      </Pane>
      <Pane name="hotspots" style={{ zIndex: 340 }} />
      {layers.heatmap && !replay && <HeatLayer patches={patches} />}
      {layers.hotspots && hotspots && <HotspotLayer data={hotspots} />}
      {layers.particles && grid && <ParticleLayer grid={grid} speed={particleSpeed} />}
      {missionBox && (
        <Rectangle
          bounds={boxBounds(missionBox)}
          interactive={false}
          pathOptions={{
            color: '#94a3b8',
            weight: 1,
            opacity: 0.35,
            dashArray: '4 6',
            fill: false,
          }}
        />
      )}
      {replay && <ReplayLayer replay={replay.data} frame={replay.frame} />}
      {!replay && (
        <LiveOverlays
          live={live}
          layers={layers}
          targets={targets}
          collected={collected}
          here={here}
          modify={modify}
        />
      )}
    </MapContainer>
  )
}

/** Patches, ghosts, routes and the vessel: everything the time slider hides. */
function LiveOverlays({
  live,
  layers,
  targets,
  collected,
  here,
  modify,
}: {
  live: LiveState
  layers: Layers
  targets: Set<string>
  collected: Set<string>
  here: LatLon | null
  modify: { moves: Record<string, LatLon>; onMove: (patchId: string, to: LatLon) => void } | null
}) {
  const { vessel, routes, patches } = live
  return (
    <>
      {layers.patches && <PatchLayer patches={patches} targets={targets} />}
      {/* Labels on one route only: the one awaiting a decision, else the one being followed. */}
      {layers.ghosts && routes.pending && (
        <GhostLayer route={routes.pending} color={COLORS.pending} labels />
      )}
      {layers.ghosts && routes.active && (
        <GhostLayer route={routes.active} color={COLORS.active} labels={!routes.pending} />
      )}
      {(layers.route || modify) && routes.pending && (
        <RouteLine
          route={modify ? withMoves(routes.pending, modify.moves) : routes.pending}
          from={null}
          skip={new Set()}
          pending
        />
      )}
      {layers.route && routes.active && (
        <RouteLine route={routes.active} from={here} skip={collected} pending={false} />
      )}
      {vessel && <VesselLayer vessel={vessel} wake={live.wake} showWake={layers.wake} />}
      {modify && routes.pending && (
        <DraggableTargets route={routes.pending} moves={modify.moves} onMove={modify.onMove} />
      )}
    </>
  )
}
