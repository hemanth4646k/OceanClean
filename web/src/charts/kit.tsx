import { Table2, TrendingUp } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Line, LineChart, ResponsiveContainer } from 'recharts'
import { Button } from '@/components/ui/button'
import { SERIES } from './style'

export interface LegendItem {
  label: string
  color: string
}

export interface TableView {
  columns: string[]
  rows: (string | number)[][]
}

/** A chart card: title, legend (>= 2 series), and a table-view twin behind a toggle. */
export function ChartCard({
  title,
  subtitle,
  legend,
  table,
  height = 220,
  children,
}: {
  title: string
  subtitle?: string
  legend?: LegendItem[]
  table: TableView
  height?: number
  children: ReactNode
}) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className="flex min-w-0 flex-col rounded-xl border bg-card p-4">
      <header className="mb-2 flex items-start gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">{title}</h3>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {legend && legend.length > 1 && (
          <ul className="ml-auto flex flex-wrap gap-3 text-xs text-muted-foreground">
            {legend.map((l) => (
              <li key={l.label} className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded" style={{ background: l.color }} />
                {l.label}
              </li>
            ))}
          </ul>
        )}
        <Button
          size="icon-sm"
          variant="ghost"
          className={legend && legend.length > 1 ? '' : 'ml-auto'}
          aria-label={asTable ? 'Show chart' : 'Show table'}
          onClick={() => setAsTable((v) => !v)}
        >
          {asTable ? <TrendingUp /> : <Table2 />}
        </Button>
      </header>
      {asTable ? (
        <div className="overflow-auto" style={{ height }}>
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card text-muted-foreground">
              <tr>
                {table.columns.map((c) => (
                  <th key={c} className="py-1 pr-3 text-left font-normal">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t border-border/50">
                  {r.map((v, j) => (
                    <td key={j} className="py-1 pr-3">
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </section>
  )
}

/** A headline number with an optional sparkline (Metrics tiles). */
export function StatTile({
  label,
  value,
  unit,
  sub,
  spark,
  tone,
}: {
  label: string
  value: string
  unit?: string
  sub?: ReactNode
  spark?: number[]
  tone?: 'warn'
}) {
  return (
    <section className="flex min-w-0 flex-col rounded-xl border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className={`text-3xl font-medium ${tone === 'warn' ? 'text-amber-300' : ''}`}>
          {value}
        </span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
      {spark && spark.length > 1 && (
        <div className="mt-2 h-8">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={spark.map((v, i) => ({ i, v }))}>
              <Line
                type="monotone"
                dataKey="v"
                stroke={SERIES[0]}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
