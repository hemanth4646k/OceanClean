import type { Patch, Vessel } from '@/lib/types'
import { FUEL_TANK_L } from '@/lib/vessel'

const fmtAge = (s: number) =>
  s < 3600 ? `${Math.max(0, Math.round(s / 60))} min` : `${(s / 3600).toFixed(1)} h`

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-24 px-4 first:pl-0 last:pr-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground tabular-nums">{sub}</div>}
    </div>
  )
}

/** A level 0..100 % with a thin bar, amber when `warn`. */
function Gauge({
  label,
  pct,
  value,
  warn,
}: {
  label: string
  pct: number
  value: string
  warn: boolean
}) {
  return (
    <div className="min-w-28 px-4 first:pl-0 last:pr-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${warn ? 'text-amber-300' : ''}`}>
        {value}
      </div>
      <div className="mt-1 h-1 rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${warn ? 'bg-amber-400' : 'bg-cyan-400'}`}
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
      </div>
    </div>
  )
}

/** Live vessel telemetry over the map: motion, hold, fuel, battery, uplink, patches left. */
export function TelemetryPanel({
  vessel,
  patches,
  link,
}: {
  vessel: Vessel | null
  patches: Patch[]
  link: { lagSimS: number; offline: boolean } | null
}) {
  const live = patches.filter((p) => p.mass_kg > 0)
  const remaining = live.reduce((s, p) => s + p.mass_kg, 0)
  return (
    <div className="flex divide-x rounded-xl border bg-card/90 px-4 py-2.5 shadow-lg backdrop-blur">
      <Cell
        label="Speed"
        value={vessel ? `${vessel.speed_kn.toFixed(1)} kn` : '—'}
        sub={vessel ? `heading ${vessel.heading_deg.toFixed(0)}°` : undefined}
      />
      <Gauge
        label="Hold"
        pct={vessel?.hold_fill_pct ?? 0}
        value={vessel ? `${vessel.hold_fill_pct.toFixed(0)}%` : '—'}
        warn={(vessel?.hold_fill_pct ?? 0) > 90}
      />
      <Gauge
        label="Fuel"
        pct={vessel ? (vessel.fuel_l / FUEL_TANK_L) * 100 : 0}
        value={vessel ? `${Math.round(vessel.fuel_l).toLocaleString()} L` : '—'}
        warn={vessel !== null && vessel.fuel_l < 0.15 * FUEL_TANK_L}
      />
      <Gauge
        label="Battery"
        pct={vessel?.battery_pct ?? 0}
        value={vessel ? `${vessel.battery_pct.toFixed(0)}%` : '—'}
        warn={vessel !== null && vessel.battery_pct < 25}
      />
      <Cell
        label="Uplink"
        value={link ? (link.offline ? 'offline' : 'online') : '—'}
        sub={link ? `last fix ${fmtAge(link.lagSimS)} ago (sim)` : undefined}
      />
      <Cell
        label="Patches left"
        value={`${live.length} / ${patches.length}`}
        sub={`${(remaining / 1000).toFixed(1)} t debris`}
      />
    </div>
  )
}
