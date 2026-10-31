import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import type { LayerKey, Layers } from '@/map/LiveMap'

const ITEMS: [LayerKey, string][] = [
  ['particles', 'Ocean currents'],
  ['heatmap', 'Debris heatmap'],
  ['hotspots', 'Convergence hotspots'],
  ['patches', 'Debris patches'],
  ['ghosts', 'Ghosts + drift lines'],
  ['route', 'Route'],
  ['wake', 'Vessel wake'],
]

export function LayerPanel({
  layers,
  onToggle,
  particleSpeed,
  onParticleSpeed,
}: {
  layers: Layers
  onToggle: (k: LayerKey, on: boolean) => void
  particleSpeed: number
  onParticleSpeed: (v: number) => void
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold">Control panel</h2>
      {ITEMS.map(([key, label]) => (
        <label key={key} className="flex cursor-pointer items-center justify-between text-sm">
          <span className="text-muted-foreground">{label}</span>
          <Switch checked={layers[key]} onCheckedChange={(on) => onToggle(key, on)} />
        </label>
      ))}
      <div className="space-y-2 pt-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Particle speed</span>
          <span className="tabular-nums">{particleSpeed.toFixed(1)}×</span>
        </div>
        <Slider
          value={[particleSpeed]}
          min={0.2}
          max={3}
          step={0.1}
          onValueChange={(v) => onParticleSpeed(Array.isArray(v) ? v[0] : v)}
        />
      </div>
    </div>
  )
}
