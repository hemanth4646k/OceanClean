import { Check, Move, TimerReset, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ms } from '@/lib/api'
import type { Hitl, Route } from '@/lib/types'

const REASONS: Record<string, string> = {
  no_route: 'The vessel has no route and is loitering.',
  target_collected: 'A target of the current route was collected.',
  deviation: 'Drift moved a target’s predicted intercept by more than 2 km.',
}

const tonnes = (kg: number) => `${(kg / 1000).toFixed(1)} t`
const yieldOf = (r: Route) => r.mass_kg / Math.max(1, r.energy_kwh)

/** Real seconds left until the proposal expires, ticking. */
function useRemaining(deadline: string | null): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 200)
    return () => clearInterval(id)
  }, [])
  return deadline === null ? null : Math.max(0, (ms(deadline) - now) / 1000)
}

function Countdown({ hitl }: { hitl: Hitl }) {
  const left = useRemaining(hitl.deadline)
  if (left === null) return null
  const frac = Math.min(1, left / hitl.timeout_s)
  const urgent = left < 10
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Sim clock held for your decision</span>
        <span className={`tabular-nums ${urgent ? 'text-amber-300' : ''}`}>
          {left > 0 ? `${Math.ceil(left)} s` : 'expiring…'}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-[width] duration-200 ease-linear ${urgent ? 'bg-amber-400' : 'bg-cyan-400'}`}
          style={{ width: `${frac * 100}%` }}
        />
      </div>
      <div className="text-[11px] text-muted-foreground">
        No decision: the proposal expires and the vessel keeps its route (or loiters).
      </div>
    </div>
  )
}

function Option({
  title,
  route,
  tone,
}: {
  title: string
  route: Route | null
  tone: 'current' | 'proposed'
}) {
  const color = tone === 'proposed' ? 'text-amber-300' : 'text-cyan-300'
  return (
    <div className="flex-1 space-y-2 rounded-lg border bg-background/40 p-3">
      <div className={`text-sm font-medium ${color}`}>{title}</div>
      {route ? (
        <>
          <div className="text-xs">{route.targets.map((t) => t.patch_id).join(' → ')}</div>
          <dl className="grid grid-cols-3 gap-1 text-xs">
            <dt className="text-muted-foreground">Debris</dt>
            <dt className="text-muted-foreground">Energy</dt>
            <dt className="text-muted-foreground">Yield</dt>
            <dd className="font-medium tabular-nums">{tonnes(route.mass_kg)}</dd>
            <dd className="font-medium tabular-nums">{(route.energy_kwh / 1000).toFixed(2)} MWh</dd>
            <dd className="font-medium tabular-nums">{yieldOf(route).toFixed(1)} kg/kWh</dd>
          </dl>
        </>
      ) : (
        <div className="text-xs text-muted-foreground">None: the vessel loiters.</div>
      )}
    </div>
  )
}

/** The AI Route Optimization decision: current vs proposed, countdown, three actions. */
export function HitlModal({
  pending,
  active,
  hitl,
  onDecide,
  onModify,
}: {
  pending: Route
  active: Route | null
  hitl: Hitl
  onDecide: (action: 'accept' | 'reject') => void
  onModify: () => void
}) {
  const gain = active ? yieldOf(pending) / yieldOf(active) - 1 : null
  return (
    <div className="pointer-events-auto w-[37rem] space-y-4 rounded-xl border border-cyan-400/30 bg-card/95 p-5 shadow-2xl backdrop-blur">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-medium tracking-wide">AI ROUTE OPTIMIZATION</h2>
        <span className="text-xs text-muted-foreground">
          Route #{pending.route_id} · planned in {pending.compute_ms.toFixed(0)} ms
        </span>
      </div>
      <div className="space-y-1 text-sm">
        <p>{REASONS[pending.reason] ?? pending.reason} An updated drift-aware route is ready.</p>
        <p>
          Expected debris:{' '}
          <span className="font-medium text-emerald-300">{tonnes(pending.mass_kg)}</span>
          {gain !== null && (
            <>
              {' '}
              · yield{' '}
              <span className={gain >= 0 ? 'text-emerald-300' : 'text-amber-300'}>
                {gain >= 0 ? '+' : ''}
                {(gain * 100).toFixed(0)}%
              </span>{' '}
              vs the current route
            </>
          )}
          .
        </p>
      </div>
      <div className="flex gap-3">
        <Option title="Current route" route={active} tone="current" />
        <Option title="AI-suggested route" route={pending} tone="proposed" />
      </div>
      <Countdown hitl={hitl} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onDecide('reject')}>
          <X /> Reject
        </Button>
        <Button variant="outline" onClick={onModify}>
          <Move /> Modify
        </Button>
        <Button onClick={() => onDecide('accept')}>
          <Check /> Accept
        </Button>
      </div>
    </div>
  )
}

/** While modifying: drag the amber targets on the map, then confirm (accepts the edit). */
export function ModifyBar({
  hitl,
  moved,
  onConfirm,
  onExtend,
  onCancel,
}: {
  hitl: Hitl
  moved: number
  onConfirm: () => void
  onExtend: () => void
  onCancel: () => void
}) {
  const left = useRemaining(hitl.deadline)
  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-xl border border-amber-400/40 bg-card/95 px-4 py-2.5 shadow-2xl backdrop-blur">
      <Move className="size-4 text-amber-300" />
      <div className="text-sm">
        Drag the target waypoints. {moved} moved
        <span className="ml-2 text-xs text-muted-foreground tabular-nums">
          {left !== null && `${Math.ceil(left)} s left`}
        </span>
      </div>
      <Button size="sm" variant="ghost" onClick={onExtend}>
        <TimerReset /> +60 s
      </Button>
      <Button size="sm" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      <Button size="sm" onClick={onConfirm}>
        <Check /> Confirm
      </Button>
    </div>
  )
}
