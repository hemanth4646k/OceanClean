import { Waves } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ClockBar } from '@/components/ClockBar'
import { LayerPanel } from '@/components/LayerPanel'
import { RouteCard } from '@/components/RouteCard'
import { StatsBar } from '@/components/StatsBar'
import { Toasts } from '@/components/Toasts'
import { Separator } from '@/components/ui/separator'
import { getJSON, ms, postJSON } from '@/lib/api'
import type { Clock, Config, Grid, Hotspots, Route } from '@/lib/types'
import { simNowMs, useLive } from '@/lib/useLive'
import { LiveMap, type LayerKey, type Layers } from '@/map/LiveMap'

const GRID_REFRESH_MS = 5000 // the u/v slice follows the sim clock
const OFFLINE_REAL_S = 10 // live state this far behind the clock (real seconds): link down

/** Retry a static fetch until it succeeds (the batch exports may not exist yet). */
function useStatic<T>(path: string): T | null {
  const [data, setData] = useState<T | null>(null)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let stop = false
    const load = () =>
      getJSON<T>(path)
        .then((d) => !stop && setData(d))
        .catch(() => {
          if (!stop) timer = setTimeout(load, 10_000)
        })
    load()
    return () => {
      stop = true
      clearTimeout(timer)
    }
  }, [path])
  return data
}

function useGrid(): Grid | null {
  const [grid, setGrid] = useState<Grid | null>(null)
  useEffect(() => {
    const load = () => getJSON<Grid>('/currents/grid').then(setGrid, () => undefined)
    load()
    const id = setInterval(load, GRID_REFRESH_MS)
    return () => clearInterval(id)
  }, [])
  return grid
}

export default function App() {
  const [live, dispatch] = useLive()
  const config = useStatic<Config>('/config')
  const hotspots = useStatic<Hotspots>('/hotspots')
  const grid = useGrid()
  const [layers, setLayers] = useState<Layers>({
    particles: true,
    heatmap: true,
    hotspots: true,
    wake: true,
    patches: true,
    ghosts: true,
    route: true,
  })
  const [particleSpeed, setParticleSpeed] = useState(1)

  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])
  const simNow = useCallback(() => simNowMs(liveRef.current, performance.now()), [])

  const fail = useCallback(
    (e: unknown) =>
      dispatch({ type: 'alert', data: { kind: 'error', level: 'warn', text: String(e), ts: null } }),
    [dispatch],
  )
  const dismiss = useCallback((id: number) => dispatch({ type: 'dismiss', id }), [dispatch])
  const control = (body: { paused?: boolean; rate?: number }) =>
    postJSON<Clock>('/sim/clock', body).then((c) => dispatch({ type: 'local-clock', data: c }), fail)
  const decide = (id: number, action: 'accept' | 'reject') =>
    postJSON<Route>(`/routes/${id}/${action}`).then(
      (r) =>
        dispatch({
          type: 'local-routes',
          data: action === 'accept' ? { active: r, pending: null } : { pending: null },
        }),
      fail,
    )

  // How far the live state trails the sim clock. The pipeline adds a few real seconds (hours of
  // sim time at fast rates); much more than that means an uplink outage is queueing telemetry.
  const { vessel, clock } = live
  const lagSimS = vessel && clock ? (ms(clock.sim_now) - ms(vessel.event_ts)) / 1000 : null
  const link =
    lagSimS === null || !clock ? null : { lagSimS, offline: lagSimS / clock.rate > OFFLINE_REAL_S }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto border-r bg-sidebar p-4">
        <div className="flex items-center gap-2">
          <Waves className="size-6 text-primary" />
          <div>
            <div className="font-semibold tracking-wide">OceanClean</div>
            <div className="text-xs text-muted-foreground">
              {config?.vessel_id ?? '…'} · North Pacific gyre
            </div>
          </div>
          <span
            className={`ml-auto size-2 rounded-full ${live.connected ? 'bg-emerald-400' : 'bg-red-400'}`}
            title={live.connected ? 'live feed connected' : 'live feed disconnected'}
          />
        </div>
        <Separator />
        <LayerPanel
          layers={layers}
          onToggle={(k: LayerKey, on: boolean) => setLayers((l) => ({ ...l, [k]: on }))}
          particleSpeed={particleSpeed}
          onParticleSpeed={setParticleSpeed}
        />
        <Separator />
        <div className="space-y-3">
          <h2 className="text-sm font-semibold">Routing</h2>
          <RouteCard active={live.routes.active} pending={live.routes.pending} onDecide={decide} />
        </div>
        {hotspots && (
          <>
            <Separator />
            <p className="text-xs text-muted-foreground">
              Hotspot cells hold {hotspots.validation.median_ratio.toFixed(1)}× the median measured
              microplastics of other cells (NOAA NCEI, {hotspots.validation.n_convergent} vs{' '}
              {hotspots.validation.n_rest} samples).
            </p>
          </>
        )}
      </aside>
      <main className="relative flex-1">
        <LiveMap
          live={live}
          layers={layers}
          missionBox={config?.mission_box ?? null}
          grid={grid}
          hotspots={hotspots}
          particleSpeed={particleSpeed}
        />
        <div className="pointer-events-none absolute inset-x-0 top-4 z-[1000] flex justify-center">
          <div className="pointer-events-auto">
            <ClockBar
              clock={live.clock}
              simNow={simNow}
              simStart={config?.sim_start ?? null}
              onControl={control}
            />
          </div>
        </div>
        <div className="absolute top-4 right-4 z-[1000]">
          <Toasts alerts={live.alerts} onDismiss={dismiss} />
        </div>
        <div className="absolute bottom-4 left-4 z-[1000]">
          <StatsBar vessel={live.vessel} patches={live.patches} link={link} />
        </div>
      </main>
    </div>
  )
}
