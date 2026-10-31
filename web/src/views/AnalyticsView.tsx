import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartCard, StatTile } from '@/charts/kit'
import { SERIES, axisProps, fmt, gridProps, tooltipProps, usePoll } from '@/charts/style'
import type { Analytics } from '@/lib/types'

const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v * 100)}`)
const shortDate = (d: string) =>
  new Date(`${d}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })

/** Admin Analytics: gold aggregates from the telemetry batch job, route decisions, validation. */
export function AnalyticsView() {
  const { data: a, error } = usePoll<Analytics>('/analytics', 30_000)
  if (!a) {
    return <p className="p-6 text-sm text-muted-foreground">{error ?? 'Loading analytics…'}</p>
  }
  const tel = a.telemetry
  const daily = (tel?.daily ?? []).map((r) => ({ ...r, y: r.kg_per_kwh ?? 0 }))
  const zones = (tel?.zones ?? []).map((r) => ({ ...r, y: r.kg_per_kwh ?? 0 }))
  const energy = zones.reduce((s, z) => s + z.energy_kwh, 0)
  const debris = zones.reduce((s, z) => s + z.collected_kg, 0)
  const decided = a.decisions.reduce((s, d) => s + d.n, 0)
  const count = (by: string) => a.decisions.filter((d) => d.by === by).reduce((s, d) => s + d.n, 0)

  return (
    <div className="grid gap-4 p-4">
      <div className="grid grid-cols-5 gap-4">
        <StatTile
          label="Debris per kWh"
          value={energy > 0 ? fmt(debris / energy, 2) : '—'}
          unit="kg/kWh"
          sub={`${fmt(debris / 1000, 1)} t for ${fmt(energy / 1000, 1)} MWh, whole mission`}
        />
        <StatTile
          label="Operator acceptance"
          value={pct(a.acceptance.operator)}
          unit={a.acceptance.operator === null ? undefined : '%'}
          sub={`${count('operator') + count('timeout')} proposals shown, timeouts count as not accepted`}
        />
        <StatTile
          label="Autopilot acceptance"
          value={pct(a.acceptance.autopilot)}
          unit={a.acceptance.autopilot === null ? undefined : '%'}
          sub={`${count('autopilot')} proposals decided by autopilot`}
        />
        <StatTile
          label="All proposals accepted"
          value={pct(a.acceptance.overall)}
          unit={a.acceptance.overall === null ? undefined : '%'}
          sub={`${decided} decided routes`}
        />
        <StatTile
          label="Hotspot validation"
          value={a.validation ? `${a.validation.median_ratio.toFixed(1)}×` : '—'}
          sub={
            a.validation
              ? `median microplastics in convergence cells vs the rest (NOAA NCEI, ${a.validation.n_convergent} vs ${a.validation.n_rest} samples)`
              : 'run the batch profile'
          }
        />
      </div>
      {!tel ? (
        <p className="rounded-xl border bg-card p-4 text-sm text-muted-foreground">
          No gold telemetry yet: run the <code>telemetry-etl</code> batch job (CLAUDE.md Commands).
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <ChartCard
              title="Debris per kWh by day"
              subtitle={`gold/telemetry_daily · computed ${tel.computed_at.slice(0, 16).replace('T', ' ')} UTC`}
              height={260}
              table={{
                columns: ['day (sim)', 'kg/kWh', 'debris kg', 'energy kWh', 'ticks'],
                rows: daily
                  .slice()
                  .reverse()
                  .map((r) => [
                    r.date,
                    fmt(r.kg_per_kwh, 2),
                    fmt(r.collected_kg),
                    fmt(r.energy_kwh),
                    r.rows,
                  ]),
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis {...axisProps} dataKey="date" tickFormatter={shortDate} minTickGap={24} />
                  <YAxis {...axisProps} width={40} />
                  <Tooltip
                    {...tooltipProps}
                    cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                    labelFormatter={(d) => `${shortDate(String(d))} (sim)`}
                    formatter={(v) => [`${fmt(Number(v), 2)} kg/kWh`, 'yield']}
                  />
                  <Bar
                    dataKey="y"
                    fill={SERIES[0]}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={28}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
          <ChartCard
            title="Debris per kWh by zone"
            subtitle="5° cells, whole mission (rolled up from gold/telemetry_daily_zone)"
            height={260}
            table={{
              columns: ['zone', 'kg/kWh', 'debris kg', 'energy kWh', 'ticks'],
              rows: zones.map((r) => [
                r.zone,
                fmt(r.kg_per_kwh, 2),
                fmt(r.collected_kg),
                fmt(r.energy_kwh),
                r.rows,
              ]),
            }}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={zones}
                layout="vertical"
                margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
              >
                <CartesianGrid {...gridProps} vertical horizontal={false} />
                <XAxis {...axisProps} type="number" />
                <YAxis {...axisProps} type="category" dataKey="zone" width={64} />
                <Tooltip
                  {...tooltipProps}
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  formatter={(v) => [`${fmt(Number(v), 2)} kg/kWh`, 'yield']}
                />
                <Bar
                  dataKey="y"
                  fill={SERIES[0]}
                  radius={[0, 4, 4, 0]}
                  barSize={18}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}
    </div>
  )
}
