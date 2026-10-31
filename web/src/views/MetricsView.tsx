import { Flame } from 'lucide-react'
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { ChartCard, StatTile } from '@/charts/kit'
import { SERIES, axisProps, fmt, gridProps, hhmm, tooltipProps, usePoll } from '@/charts/style'
import { ms, postJSON } from '@/lib/api'
import type { Metrics, MetricPoint, QueryName, StoredAlert } from '@/lib/types'
import { FUEL_TANK_L } from '@/lib/vessel'

const QUERIES: { key: QueryName; label: string; color: string }[] = [
  { key: 'telemetry', label: 'telemetry (dual write)', color: SERIES[0] },
  { key: 'debris_survey', label: 'debris surveys', color: SERIES[1] },
  { key: 'windows', label: '5-min windows', color: SERIES[2] },
]

type Wide = { t: number } & Partial<Record<QueryName, number | null>>

/** Long rows (t, query, value) -> one row per bucket with a column per query. */
/** Long rows (t, query, value) -> one row per bucket with a column per query. Buckets with no
 * batches at all (stream stopped, clock paused) become null rows, so lines break at gaps
 * instead of drawing a straight line across them. */
function pivot(
  series: MetricPoint[],
  bucketS: number,
  value: (p: MetricPoint) => number | null,
): Wide[] {
  const by = new Map<number, Wide>()
  for (const p of series) {
    const t = ms(p.t)
    const row = by.get(t) ?? { t }
    row[p.query] = value(p)
    by.set(t, row)
  }
  const rows = [...by.values()].sort((a, b) => a.t - b.t)
  const out: Wide[] = []
  const step = bucketS * 1000
  for (const r of rows) {
    const prev = out.at(-1)
    if (prev && r.t - prev.t > step) {
      out.push({ t: prev.t + step, ...Object.fromEntries(QUERIES.map((q) => [q.key, null])) })
    }
    out.push(r)
  }
  return out
}

function QueryChart({
  title,
  subtitle,
  data,
  unit,
}: {
  title: string
  subtitle: string
  data: Wide[]
  unit: string
}) {
  return (
    <ChartCard
      title={title}
      subtitle={subtitle}
      legend={QUERIES.map((q) => ({ label: q.label, color: q.color }))}
      table={{
        columns: ['time (UTC)', ...QUERIES.map((q) => q.key)],
        rows: data
          .slice(-60)
          .reverse()
          .map((r) => [hhmm(r.t), ...QUERIES.map((q) => fmt(r[q.key], 1))]),
      }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis
            {...axisProps}
            dataKey="t"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={hhmm}
            minTickGap={40}
          />
          <YAxis {...axisProps} width={48} />
          <Tooltip
            {...tooltipProps}
            labelFormatter={(t) => `${hhmm(Number(t))} UTC`}
            formatter={(v, name) => [`${fmt(Number(v), 1)} ${unit}`, String(name)]}
          />
          {QUERIES.map((q) => (
            <Line
              key={q.key}
              dataKey={q.key}
              name={q.label}
              stroke={q.color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

const simTime = (iso: string) => `${iso.slice(5, 16).replace('T', ' ')} UTC`

function FaultCard({ latest }: { latest: StoredAlert | undefined }) {
  const [until, setUntil] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inject = () => {
    setBusy(true)
    postJSON<{ fuel_leak_until: string }>('/sim/fault', { hours: 6 })
      .then((r) => setUntil(r.fuel_leak_until))
      .finally(() => setBusy(false))
  }
  return (
    <section className="flex flex-col justify-between gap-2 rounded-xl border bg-card p-4">
      <div className="text-sm text-muted-foreground">Fault injection</div>
      <Button variant="outline" onClick={inject} disabled={busy}>
        <Flame /> Inject fuel leak (6 h)
      </Button>
      <p className="text-xs text-muted-foreground">
        {until
          ? `Leaking until ${until.replace('T', ' ').replace('Z', ' UTC')} (sim). `
          : '1.5× fuel for the same power. '}
        Shows only while the engine runs, not when loitering on battery.
      </p>
      {latest && (
        <p className="text-xs text-amber-300">
          Last anomaly ({simTime(latest.ts)} sim): {latest.text.replace(/ on OC-\d+/, '')}
        </p>
      )}
    </section>
  )
}

/** Admin Metrics: pipeline health from the StreamingQueryListener, vessel energy. */
export function MetricsView() {
  const { data: m, error } = usePoll<Metrics>('/metrics?minutes=15&hours=48', 5000)
  if (!m) {
    return <p className="p-6 text-sm text-muted-foreground">{error ?? 'Loading metrics…'}</p>
  }
  const rate = pivot(m.series, m.bucket_s, (p) => p.rows_per_s)
  const duration = pivot(m.series, m.bucket_s, (p) => p.duration_ms)
  // The newest bucket is still filling; tiles use complete buckets only.
  const tel = m.series.filter((p) => p.query === 'telemetry').slice(0, -1)
  const latest = Object.fromEntries(m.latest.map((q) => [q.query, q]))
  const lags = m.latest.map((q) => q.kafka_lag ?? 0)
  const lake = Object.fromEntries(m.lake.map((d) => [d.dataset, d.rows]))
  const lagByBucket = [...pivot(m.series, m.bucket_s, (p) => p.kafka_lag).values()].map((r) =>
    Math.max(0, ...QUERIES.map((q) => r[q.key] ?? 0)),
  )

  const hourly = m.hourly.map((h) => ({
    t: ms(h.hour),
    fuel: (h.fuel_l / FUEL_TANK_L) * 100,
    battery: h.battery_pct,
  }))
  let e = 0
  let d = 0
  const yieldCurve = [{ e: 0, d: 0 }]
  for (const h of m.hourly) {
    e += h.energy_kwh / 1000
    d += h.collected_kg / 1000
    yieldCurve.push({ e, d })
  }
  const anomalies = m.hourly.reduce((s, h) => s + h.anomalies, 0)
  const simHour = (t: number) =>
    new Date(t).toLocaleString('en-GB', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      timeZone: 'UTC',
    })

  return (
    <div className="grid gap-4 p-4">
      <div className="grid grid-cols-5 gap-4">
        <StatTile
          label="Events / s"
          value={fmt(tel.at(-1)?.rows_per_s, 0)}
          sub={`telemetry query, ${m.bucket_s} s buckets`}
          spark={tel.map((p) => p.rows_per_s)}
        />
        <StatTile
          label="Kafka lag"
          value={fmt(Math.max(0, ...lags))}
          unit="offsets"
          sub="max behind latest, all queries"
          spark={lagByBucket}
          tone={Math.max(0, ...lags) > 1000 ? 'warn' : undefined}
        />
        <StatTile
          label="Micro-batch duration"
          value={fmt(latest.telemetry?.duration_ms)}
          unit="ms"
          sub={`telemetry batch #${latest.telemetry?.batch_id ?? '—'}`}
          spark={tel.map((p) => p.duration_ms ?? 0)}
        />
        <StatTile
          label="Lake rows"
          value={fmt(lake['bronze/telemetry'])}
          sub={
            <>
              bronze telemetry · silver {fmt(lake['silver/telemetry'])} · surveys{' '}
              {fmt(lake['bronze/debris_survey'])}
            </>
          }
        />
        <FaultCard latest={m.alerts.find((a) => a.kind === 'fuel_anomaly')} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <QueryChart
          title="Events per second"
          subtitle="Rows read per query, last 15 min (wall time); the windows query reads the telemetry topic too"
          data={rate}
          unit="rows/s"
        />
        <QueryChart
          title="Micro-batch duration"
          subtitle="Trigger execution time per query, last 15 min (wall time)"
          data={duration}
          unit="ms"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <ChartCard
          title="Fuel and battery"
          subtitle={`Last 48 sim hours, % of tank (${FUEL_TANK_L.toLocaleString()} L) and of charge · ${anomalies} fuel-burn anomal${anomalies === 1 ? 'y' : 'ies'}`}
          legend={[
            { label: 'fuel', color: SERIES[0] },
            { label: 'battery', color: SERIES[1] },
          ]}
          table={{
            columns: ['sim hour (UTC)', 'fuel %', 'battery %'],
            rows: hourly
              .slice()
              .reverse()
              .map((h) => [simHour(h.t), fmt(h.fuel, 1), fmt(h.battery, 1)]),
          }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={hourly} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis
                {...axisProps}
                dataKey="t"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickFormatter={simHour}
                minTickGap={60}
              />
              <YAxis {...axisProps} width={40} domain={[0, 100]} unit="%" />
              <Tooltip
                {...tooltipProps}
                labelFormatter={(t) => `${simHour(Number(t))}:00 UTC (sim)`}
                formatter={(v, name) => [`${fmt(Number(v), 1)} %`, String(name)]}
              />
              <Line
                dataKey="fuel"
                name="fuel"
                stroke={SERIES[0]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="battery"
                name="battery"
                stroke={SERIES[1]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Debris removed vs energy used"
          subtitle="Cumulative over the last 48 sim hours; the slope is the yield (t per MWh)"
          table={{
            columns: ['energy MWh', 'debris t'],
            rows: yieldCurve
              .slice(1)
              .reverse()
              .map((p) => [fmt(p.e, 2), fmt(p.d, 2)]),
          }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={yieldCurve} margin={{ top: 8, right: 8, bottom: 12, left: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis
                {...axisProps}
                dataKey="e"
                type="number"
                domain={[0, 'dataMax']}
                tickFormatter={(v: number) => v.toFixed(1)}
                unit=" MWh"
              />
              <YAxis {...axisProps} width={48} unit=" t" />
              <Tooltip
                {...tooltipProps}
                labelFormatter={(v) => `${fmt(Number(v), 2)} MWh used`}
                formatter={(v) => [`${fmt(Number(v), 2)} t`, 'debris removed']}
              />
              <Line
                dataKey="d"
                stroke={SERIES[0]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
      <section className="rounded-xl border bg-card p-4">
        <h3 className="mb-2 text-sm font-medium">Recent alerts</h3>
        {m.alerts.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            None yet. Inject a fuel leak while the vessel is under way to raise one.
          </p>
        ) : (
          <ul className="space-y-1 text-sm">
            {m.alerts.map((a) => (
              <li key={a.alert_id} className="flex gap-3">
                <span className="w-32 shrink-0 text-xs text-muted-foreground tabular-nums">
                  {simTime(a.ts)}
                </span>
                <span className={a.level === 'warn' ? 'text-amber-300' : ''}>{a.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
