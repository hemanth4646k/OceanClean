import type { Patch, Vessel } from '@/lib/types'

const fmtAge = (s: number) =>
  s < 3600 ? `${Math.max(0, Math.round(s / 60))} min` : `${(s / 3600).toFixed(1)} h`

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="px-4 first:pl-0 last:pr-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground tabular-nums">{sub}</div>}
    </div>
  )
}

export function StatsBar({
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
      <Stat
        label="Patches left"
        value={`${live.length} / ${patches.length}`}
        sub={`${(remaining / 1000).toFixed(1)} t debris`}
      />
      <Stat
        label="Speed"
        value={vessel ? `${vessel.speed_kn.toFixed(1)} kn` : '—'}
        sub={vessel ? `heading ${vessel.heading_deg.toFixed(0)}°` : undefined}
      />
      <Stat label="Hold" value={vessel ? `${vessel.hold_fill_pct.toFixed(0)}%` : '—'} />
      <Stat label="Fuel" value={vessel ? `${Math.round(vessel.fuel_l).toLocaleString()} L` : '—'} />
      <Stat label="Battery" value={vessel ? `${vessel.battery_pct.toFixed(0)}%` : '—'} />
      <Stat
        label="Uplink"
        value={link ? (link.offline ? 'offline' : 'online') : '—'}
        sub={link ? `last fix ${fmtAge(link.lagSimS)} ago (sim)` : undefined}
      />
    </div>
  )
}
