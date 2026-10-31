import L from 'leaflet'
import { Fragment, useMemo } from 'react'
import { CircleMarker, Marker, Polyline, Rectangle, Tooltip } from 'react-leaflet'
import { ms } from '@/lib/api'
import type { Hotspots, LatLon, Patch, Route, Vessel } from '@/lib/types'
import { COLORS } from './colors'

export function HotspotLayer({ data }: { data: Hotspots }) {
  const h = data.cell_deg / 2
  return data.hotspots.map((c) => (
    <Rectangle
      key={c.rank}
      pane="hotspots"
      bounds={[
        [c.lat - h, c.lon - h],
        [c.lat + h, c.lon + h],
      ]}
      pathOptions={{
        stroke: false,
        fillColor: COLORS.hotspot,
        fillOpacity: 0.04 + 0.16 * Math.max(0, (c.frac_convergent - 0.5) * 2),
      }}
    >
      <Tooltip className="oc-tip" sticky>
        Convergence hotspot #{c.rank} · converging {(c.frac_convergent * 100).toFixed(0)}% of{' '}
        {c.n_days} days
        {c.mp_median !== null && ` · microplastics ${c.mp_median.toFixed(3)} pcs/m³`}
      </Tooltip>
    </Rectangle>
  ))
}

export function PatchLayer({ patches, targets }: { patches: Patch[]; targets: Set<string> }) {
  const max = Math.max(1, ...patches.map((p) => p.mass_kg))
  return patches.map((p) => {
    const live = p.mass_kg > 0
    return (
      <CircleMarker
        key={p.patch_id}
        center={[p.lat, p.lon]}
        radius={live ? 4 + 7 * Math.sqrt(p.mass_kg / max) : 3}
        pathOptions={{
          color: targets.has(p.patch_id) ? '#fff7ed' : live ? COLORS.patch : COLORS.collected,
          weight: targets.has(p.patch_id) ? 2 : 1,
          fillColor: live ? COLORS.patch : COLORS.collected,
          fillOpacity: live ? 0.75 : 0.25,
          opacity: live ? 0.9 : 0.35,
        }}
      >
        <Tooltip className="oc-tip">
          {p.patch_id} · {live ? `${(p.mass_kg / 1000).toFixed(1)} t` : 'collected'}
        </Tooltip>
      </CircleMarker>
    )
  })
}

/** Ghosts (predicted intercept) and the dashed drift line from the surveyed position. */
export function GhostLayer({
  route,
  color,
  labels,
}: {
  route: Route
  color: string
  labels: boolean
}) {
  const planned = ms(route.planned_at)
  return route.targets.map((t, i) => (
    <Fragment key={`${route.route_id}-${t.patch_id}`}>
      <Polyline
        positions={t.drift}
        pathOptions={{ color: COLORS.ghost, weight: 1.2, opacity: 0.7, dashArray: '3 5' }}
      />
      <CircleMarker
        center={[t.predicted.lat, t.predicted.lon]}
        radius={8}
        pathOptions={{ color, weight: 1.5, dashArray: '3 3', fillOpacity: 0.08, fillColor: color }}
      >
        {labels && (
          <Tooltip className="oc-label" direction="right" offset={[8, 0]} permanent>
            {i + 1}. {t.patch_id} ghost · +{((ms(t.predicted.ts) - planned) / 3.6e6).toFixed(0)} h
          </Tooltip>
        )}
      </CircleMarker>
    </Fragment>
  ))
}

/** The route line: from the vessel (active) or the plan's start (pending) through the targets. */
export function RouteLine({
  route,
  from,
  skip,
  pending,
}: {
  route: Route
  from: LatLon | null
  skip: Set<string>
  pending: boolean
}) {
  const pts: LatLon[] = route.waypoints
    .filter((w) => w.kind === 'target' && !skip.has(w.patch_id ?? ''))
    .map((w) => [w.lat, w.lon])
  const start = from ?? [route.waypoints[0].lat, route.waypoints[0].lon]
  return (
    <Polyline
      positions={[start, ...pts]}
      pathOptions={{
        color: pending ? COLORS.pending : COLORS.active,
        weight: pending ? 2 : 2.5,
        opacity: 0.9,
        dashArray: pending ? '8 6' : undefined,
      }}
    />
  )
}

function vesselIcon(heading: number): L.DivIcon {
  return L.divIcon({
    className: '',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<svg width="26" height="26" viewBox="0 0 26 26" style="transform:rotate(${heading}deg)">
      <circle cx="13" cy="13" r="11" fill="rgba(34,211,238,0.15)" stroke="rgba(34,211,238,0.5)"/>
      <path d="M13 3 L19 20 L13 16.5 L7 20 Z" fill="#22d3ee" stroke="#0a1520" stroke-width="1"/>
    </svg>`,
  })
}

export function VesselLayer({
  vessel,
  wake,
  showWake,
}: {
  vessel: Vessel
  wake: LatLon[]
  showWake: boolean
}) {
  const heading = Math.round(vessel.heading_deg)
  const icon = useMemo(() => vesselIcon(heading), [heading])
  return (
    <>
      {showWake && wake.length > 1 && (
        <Polyline
          positions={[...wake, [vessel.lat, vessel.lon]]}
          pathOptions={{ color: COLORS.wake, weight: 2, opacity: 0.55 }}
        />
      )}
      <Marker position={[vessel.lat, vessel.lon]} icon={icon} zIndexOffset={1000}>
        <Tooltip className="oc-tip" direction="top" offset={[0, -12]}>
          {vessel.vessel_id} · {vessel.speed_kn.toFixed(1)} kn · hold{' '}
          {vessel.hold_fill_pct.toFixed(0)}%
        </Tooltip>
      </Marker>
    </>
  )
}

const handleIcon = L.divIcon({
  className: '',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
  html: `<div style="width:18px;height:18px;border-radius:9999px;background:${COLORS.pending};
    border:2px solid #fff7ed;box-shadow:0 0 0 4px rgba(251,191,36,0.25);cursor:grab"></div>`,
})

/** Modify: the pending route's target waypoints as draggable handles. */
export function DraggableTargets({
  route,
  moves,
  onMove,
}: {
  route: Route
  moves: Record<string, LatLon>
  onMove: (patchId: string, to: LatLon) => void
}) {
  return route.waypoints
    .filter((w) => w.kind === 'target' && w.patch_id)
    .map((w) => {
      const id = w.patch_id as string
      const at = moves[id] ?? [w.lat, w.lon]
      return (
        <Marker
          key={id}
          position={at}
          icon={handleIcon}
          draggable
          zIndexOffset={2000}
          eventHandlers={{
            dragend: (e) => {
              const p = (e.target as L.Marker).getLatLng()
              onMove(id, [p.lat, p.lng])
            },
          }}
        >
          <Tooltip className="oc-label" direction="right" offset={[10, 0]} permanent>
            {id}
          </Tooltip>
        </Marker>
      )
    })
}
