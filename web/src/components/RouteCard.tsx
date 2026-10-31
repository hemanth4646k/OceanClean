import { Bot } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import type { Hitl, Route } from '@/lib/types'

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

/** Routing in the sidebar: the autopilot switch, the route being followed, any proposal. */
export function RouteCard({
  active,
  pending,
  hitl,
  onAutopilot,
}: {
  active: Route | null
  pending: Route | null
  hitl: Hitl | null
  onAutopilot: (on: boolean) => void
}) {
  return (
    <div className="space-y-4">
      <label className="flex cursor-pointer items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <Bot className="size-4 text-muted-foreground" />
          Autopilot
        </span>
        <Switch
          checked={hitl?.autopilot ?? false}
          disabled={!hitl}
          onCheckedChange={(on) => onAutopilot(on)}
        />
      </label>
      <p className="text-xs text-muted-foreground">
        {hitl?.autopilot
          ? 'Every proposal is accepted at once, including a fresh plan after each collection.'
          : `You decide each proposal; the sim clock waits up to ${hitl?.timeout_s ?? 30} s.`}
      </p>
      {pending && (
        <div className="flex items-center justify-between rounded-lg border border-amber-400/40 bg-amber-400/5 px-3 py-2 text-sm">
          <span>Proposal #{pending.route_id}</span>
          <Badge variant="outline" className="border-amber-400/50 text-amber-300">
            awaiting decision
          </Badge>
        </div>
      )}
      {active ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Active route #{active.route_id}</span>
            <Badge className="bg-cyan-400/15 text-cyan-300">
              {active.decided_by === 'autopilot' ? 'autopilot' : 'operator'}
            </Badge>
          </div>
          <Summary route={active} />
        </div>
      ) : (
        !pending && <p className="text-sm text-muted-foreground">No route: the vessel loiters.</p>
      )}
    </div>
  )
}
