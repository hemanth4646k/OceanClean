import { CircleMarker, Polyline } from 'react-leaflet'
import type { Replay } from '@/lib/types'
import { COLORS } from './colors'

const TRAIL = 28 // frames of track behind each parcel (7 days at 6 h)

/** Debris parcels at one replay frame, each with the trail it drifted along to get there. */
export function ReplayLayer({ replay, frame }: { replay: Replay; frame: number }) {
  return replay.parcels
    .map((p) => (
      <Polyline
        key={p.id}
        positions={p.track.slice(Math.max(0, frame - TRAIL), frame + 1)}
        pathOptions={{ color: COLORS.parcel, weight: 1.2, opacity: 0.45 }}
        interactive={false}
      />
    ))
    .concat(
      replay.parcels.map((p) => (
        <CircleMarker
          key={`${p.id}-dot`}
          center={p.track[frame]}
          radius={3}
          pathOptions={{
            color: COLORS.parcel,
            weight: 1,
            fillColor: COLORS.parcel,
            fillOpacity: 0.9,
          }}
          interactive={false}
        />
      )),
    )
}
