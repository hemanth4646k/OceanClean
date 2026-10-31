import { Check, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Route } from '@/lib/types'

function Summary({ route }: { route: Route }) {
  return (
    <>
      <div className="text-sm font-medium">{route.targets.map((t) => t.patch_id).join(' → ')}</div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <Stat label="Debris" value={`${(route.mass_kg / 1000).toFixed(1)} t`} />
        <Stat label="Energy" value={`${(route.energy_kwh / 1000).toFixed(2)} MWh`} />
        <Stat
          label="Yield"
          value={`${(route.mass_kg / Math.max(1, route.energy_kwh)).toFixed(1)} kg/kWh`}
        />
      </div>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  )
}

/**
 * Pending proposal with Accept / Reject, and the active route. A stand-in for the M5 modal
 * (countdown, Modify, clock pause), so routes can be accepted from the map.
 */
export function RouteCard({
  active,
  pending,
  onDecide,
}: {
  active: Route | null
  pending: Route | null
  onDecide: (id: number, action: 'accept' | 'reject') => void
}) {
  if (!active && !pending) {
    return <p className="text-sm text-muted-foreground">No route: the vessel loiters.</p>
  }
  return (
    <div className="space-y-4">
      {pending && (
        <div className="space-y-2 rounded-lg border border-amber-400/40 bg-amber-400/5 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Proposal #{pending.route_id}</span>
            <Badge variant="outline" className="border-amber-400/50 text-amber-300">
              {pending.reason.replace('_', ' ')}
            </Badge>
          </div>
          <Summary route={pending} />
          <div className="text-xs text-muted-foreground">
            Planned in {pending.compute_ms.toFixed(0)} ms
          </div>
          <div className="flex gap-2">
            <Button size="sm" className="flex-1" onClick={() => onDecide(pending.route_id, 'accept')}>
              <Check /> Accept
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="flex-1"
              onClick={() => onDecide(pending.route_id, 'reject')}
            >
              <X /> Reject
            </Button>
          </div>
        </div>
      )}
      {active && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Active route #{active.route_id}</span>
            <Badge className="bg-cyan-400/15 text-cyan-300">following</Badge>
          </div>
          <Summary route={active} />
        </div>
      )}
    </div>
  )
}
