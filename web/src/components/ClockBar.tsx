import { Pause, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ms } from '@/lib/api'
import type { Clock } from '@/lib/types'

const RATES = [60, 600, 1800, 3600, 7200]
const rateLabel = (r: number) => (r >= 3600 ? `${r / 3600} h/s` : `${r / 60} min/s`)

function fmt(t: number): string {
  const d = new Date(t)
  const date = d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
  const time = d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  })
  return `${date.toUpperCase()} · ${time} UTC`
}

/** Sim clock: extrapolated time, mission day, play/pause and speed (POST /sim/clock). */
export function ClockBar({
  clock,
  simNow,
  simStart,
  onControl,
}: {
  clock: Clock | null
  simNow: () => number | null
  simStart: string | null
  onControl: (c: { paused?: boolean; rate?: number }) => void
}) {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    const id = setInterval(() => setNow(simNow()), 200)
    return () => clearInterval(id)
  }, [simNow])
  const day = now !== null && simStart ? (now - ms(simStart)) / 86_400_000 : null
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/90 px-3 py-2 shadow-lg backdrop-blur">
      <Button
        size="icon"
        variant="secondary"
        disabled={!clock}
        onClick={() => clock && onControl({ paused: !clock.paused })}
        aria-label={clock?.paused ? 'Play' : 'Pause'}
      >
        {clock?.paused ? <Play /> : <Pause />}
      </Button>
      <div className="min-w-56 text-center">
        <div className="text-sm font-medium tabular-nums">{now !== null ? fmt(now) : '—'}</div>
        <div className="text-xs text-muted-foreground tabular-nums">
          {day !== null ? `Mission day ${day.toFixed(1)}` : 'waiting for the simulator'}
          {clock?.paused && ' · paused'}
          {clock?.hitl_hold && !clock.paused && (
            <span className="text-amber-300"> · held for decision</span>
          )}
        </div>
      </div>
      <div className="flex gap-1">
        {RATES.map((r) => (
          <Button
            key={r}
            size="sm"
            variant={clock?.rate === r ? 'default' : 'ghost'}
            disabled={!clock}
            onClick={() => onControl({ rate: r })}
          >
            {rateLabel(r)}
          </Button>
        ))}
      </div>
    </div>
  )
}
