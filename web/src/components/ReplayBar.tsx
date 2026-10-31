import { Pause, Play, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import type { Replay } from '@/lib/types'

const day = (iso: string) =>
  new Date(iso)
    .toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      timeZone: 'UTC',
    })
    .toUpperCase()

/** Time slider over the replay window: play/pause, scrub, and the real day of currents shown. */
export function ReplayBar({
  replay,
  frame,
  playing,
  onFrame,
  onPlaying,
  onClose,
}: {
  replay: Replay
  frame: number
  playing: boolean
  onFrame: (f: number) => void
  onPlaying: (on: boolean) => void
  onClose: () => void
}) {
  const f = replay.frames[frame]
  const days = (frame * replay.step_s) / 86_400
  return (
    <div className="flex w-[34rem] items-center gap-3 rounded-xl border border-orange-400/40 bg-card/90 px-3 py-2 shadow-lg backdrop-blur">
      <Button
        size="icon"
        variant="secondary"
        onClick={() => onPlaying(!playing)}
        aria-label={playing ? 'Pause replay' : 'Play replay'}
      >
        {playing ? <Pause /> : <Play />}
      </Button>
      <div className="flex-1 space-y-1.5">
        <div className="flex justify-between text-xs">
          <span className="font-medium tabular-nums">
            {day(f.data_t)} · day {days.toFixed(1)}
          </span>
          <span className="text-muted-foreground">
            {Math.round((replay.frames.length * replay.step_s) / 86_400)}-day drift replay · NOAA
            SCUD daily currents · {replay.parcels.length} parcels
          </span>
        </div>
        <Slider
          value={[frame]}
          min={0}
          max={replay.frames.length - 1}
          step={1}
          onValueChange={(v) => onFrame(Array.isArray(v) ? v[0] : v)}
        />
      </div>
      <Button size="icon" variant="ghost" onClick={onClose} aria-label="Back to live">
        <X />
      </Button>
    </div>
  )
}
