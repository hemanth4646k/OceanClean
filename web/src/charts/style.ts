import { useEffect, useState } from 'react'
import { getJSON } from '@/lib/api'

// Dark categorical slots in fixed order (dataviz reference palette), validated on the card
// surface #0d1926: CVD dE 9.4, normal-vision dE 26.5, all >= 3:1. Colour follows the entity.
export const SERIES = ['#3987e5', '#d95926', '#199e70'] as const
export const INK = { muted: '#898781', grid: '#26313e', axis: '#384656', secondary: '#c3c2b7' }

export const axisProps = {
  stroke: INK.axis,
  tick: { fill: INK.muted, fontSize: 11 },
  tickLine: false,
} as const

export const gridProps = { stroke: INK.grid, vertical: false } as const

export const tooltipProps = {
  contentStyle: {
    background: 'rgba(13, 25, 38, 0.96)',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 8,
    fontSize: 12,
  },
  labelStyle: { color: INK.secondary },
  itemStyle: { color: '#f0efec' },
  cursor: { stroke: INK.axis },
} as const

export const hhmm = (t: number) =>
  new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

export const fmt = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || !Number.isFinite(v)
    ? '—'
    : v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })

/** Poll a GET endpoint; keeps the last good response while refetching (no skeleton flash). */
export function usePoll<T>(
  path: string,
  everyMs: number,
): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let stop = false
    const load = () =>
      getJSON<T>(path).then(
        (d) => {
          if (!stop) {
            setData(d)
            setError(null)
          }
        },
        (e: unknown) => !stop && setError(String(e)),
      )
    load()
    const id = setInterval(load, everyMs)
    return () => {
      stop = true
      clearInterval(id)
    }
  }, [path, everyMs])
  return { data, error }
}
