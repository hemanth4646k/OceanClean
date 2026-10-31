import { History, Waves } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ClockBar } from '@/components/ClockBar'
import { HitlModal, ModifyBar } from '@/components/HitlModal'
import { LayerPanel } from '@/components/LayerPanel'
import { ReplayBar } from '@/components/ReplayBar'
import { RouteCard } from '@/components/RouteCard'
import { TelemetryPanel } from '@/components/TelemetryPanel'
import { Toasts } from '@/components/Toasts'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { getJSON, ms, postJSON } from '@/lib/api'
import type { Clock, Config, Grid, Hitl, Hotspots, LatLon, Replay, Route } from '@/lib/types'
import { simNowMs, useLive } from '@/lib/useLive'
import { LiveMap, type LayerKey, type Layers } from '@/map/LiveMap'
import { AnalyticsView } from '@/views/AnalyticsView'
import { MetricsView } from '@/views/MetricsView'

type Role = 'operator' | 'admin'
type Tab = 'map' | 'metrics' | 'analytics'
const TABS: { key: Tab; label: string; admin: boolean }[] = [
  { key: 'map', label: 'Live map', admin: false },
  { key: 'metrics', label: 'Metrics', admin: true },
  { key: 'analytics', label: 'Analytics', admin: true },
]

const GRID_REFRESH_MS = 5000 // the u/v slice follows the sim clock
const OFFLINE_REAL_S = 10 // live state this far behind the clock (real seconds): link down
const REPLAY_FRAME_MS = 150 // 6 sim-hours per frame: the 45-day window plays in about 27 s

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

/** The u/v slice at sim time t (a replay frame), else following the sim clock. */
function useGrid(t: string | null): Grid | null {
  const [grid, setGrid] = useState<Grid | null>(null)
  useEffect(() => {
    let stale = false
    const path = t ? `/currents/grid?t=${encodeURIComponent(t)}` : '/currents/grid'
    const load = () =>
      getJSON<Grid>(path).then(
        (g) => !stale && setGrid(g),
        () => undefined,
      )
    load()
    const id = t ? undefined : setInterval(load, GRID_REFRESH_MS)
    return () => {
      stale = true
      clearInterval(id)
    }
  }, [t])
  return grid
}

/** The time slider: frames load on first open; while playing, the frame advances and loops. */
interface ReplayState {
  data: Replay | null
  frame: number
  playing: boolean
  setFrame: (f: number) => void
  setPlaying: (on: boolean) => void
}

function useReplay(open: boolean): ReplayState {
  const [data, setData] = useState<Replay | null>(null)
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    if (open && !data) getJSON<Replay>('/replay').then(setData, () => undefined)
  }, [open, data])
  const n = data?.frames.length ?? 0
  useEffect(() => {
    if (!open || !playing || n === 0) return
    const id = setInterval(() => setFrame((f) => (f + 1) % n), REPLAY_FRAME_MS)
    return () => clearInterval(id)
  }, [open, playing, n])
  return {
    data: open ? data : null,
    frame: Math.min(frame, Math.max(0, n - 1)),
    playing,
    setFrame,
    setPlaying,
  }
}

function tabFromHash(): Tab {
  const h = location.hash.slice(1)
  return TABS.some((t) => t.key === h) ? (h as Tab) : 'map'
}

export default function App() {
  const [live, dispatch] = useLive()
  const config = useStatic<Config>('/config')
  const hotspots = useStatic<Hotspots>('/hotspots')
  const [replayOpen, setReplayOpen] = useState(false)
  const replay = useReplay(replayOpen)
  const grid = useGrid(replay.data ? replay.data.frames[replay.frame].t : null)
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
  // The tab lives in the URL hash (#metrics, #analytics), so views can be linked and reloaded.
  const [tab, setTabState] = useState<Tab>(tabFromHash)
  const [role, setRole] = useState<Role>(() => (tabFromHash() === 'map' ? 'operator' : 'admin'))
  const setTab = useCallback((t: Tab) => {
    setTabState(t)
    history.replaceState(null, '', t === 'map' ? location.pathname : `#${t}`)
  }, [])
  const [modifying, setModifying] = useState<{
    routeId: number
    moves: Record<string, LatLon>
  } | null>(null)

  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])
  const simNow = useCallback(() => simNowMs(liveRef.current, performance.now()), [])

  const fail = useCallback(
    (e: unknown) =>
      dispatch({
        type: 'alert',
        data: { kind: 'error', level: 'warn', text: String(e), ts: null },
      }),
    [dispatch],
  )
  const dismiss = useCallback((id: number) => dispatch({ type: 'dismiss', id }), [dispatch])
  const control = (body: { paused?: boolean; rate?: number }) =>
    postJSON<Clock>('/sim/clock', body).then(
      (c) => dispatch({ type: 'local-clock', data: c }),
      fail,
    )
  const decide = (id: number, action: 'accept' | 'reject') =>
    postJSON<Route>(`/routes/${id}/${action}`).then(
      (r) =>
        dispatch({
          type: 'local-routes',
          data: action === 'accept' ? { active: r, pending: null } : { pending: null },
        }),
      fail,
    )
  const setAutopilot = (on: boolean) =>
    postJSON<Hitl>('/hitl', { autopilot: on }).then(
      (h) => dispatch({ type: 'local-hitl', data: h }),
      fail,
    )
  const extend = (id: number) => postJSON(`/routes/${id}/extend`).catch(fail)
  const startModify = (id: number) => {
    void extend(id)
    setModifying({ routeId: id, moves: {} })
    setTab('map')
  }
  const confirmModify = (id: number, moves: Record<string, LatLon>) =>
    postJSON<Route>(`/routes/${id}/modify`, { waypoints: moves }).then(
      (r) => dispatch({ type: 'local-routes', data: { active: r, pending: null } }),
      fail,
    )

  // A modification applies only to the proposal it started on; a decision or expiry ends it.
  const { pending, active } = live.routes
  const mod = modifying && pending?.route_id === modifying.routeId ? modifying : null
  const showModal = pending && live.hitl && !live.hitl.autopilot && !mod

  // How far the live state trails the sim clock. The pipeline adds a few real seconds (hours of
  // sim time at fast rates); much more than that means an uplink outage is queueing telemetry.
  const { vessel, clock } = live
  const lagSimS = vessel && clock ? (ms(clock.sim_now) - ms(vessel.event_ts)) / 1000 : null
  const link =
    lagSimS === null || !clock ? null : { lagSimS, offline: lagSimS / clock.rate > OFFLINE_REAL_S }

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <header className="flex h-12 shrink-0 items-center gap-6 border-b bg-sidebar px-4">
        <div className="flex items-center gap-2">
          <Waves className="size-5 text-primary" />
          <span className="font-semibold tracking-wide">OceanClean</span>
          <span className="text-xs text-muted-foreground">
            {config?.vessel_id ?? '…'} · North Pacific gyre
          </span>
        </div>
        <nav className="flex gap-1">
          {TABS.filter((t) => role === 'admin' || !t.admin).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`rounded-md px-3 py-1.5 text-sm ${tab === t.key ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {live.hitl && (
            <span
              className={`rounded-md border px-2 py-0.5 text-xs ${live.hitl.autopilot ? 'border-emerald-400/40 text-emerald-300' : 'border-amber-400/40 text-amber-300'}`}
            >
              AUTOPILOT: {live.hitl.autopilot ? 'ON' : 'OFF'}
            </span>
          )}
          <div className="flex rounded-md border p-0.5 text-xs" role="radiogroup" aria-label="Role">
            {(['operator', 'admin'] as const).map((r) => (
              <button
                key={r}
                role="radio"
                aria-checked={role === r}
                onClick={() => {
                  setRole(r)
                  if (r === 'operator') setTab('map')
                }}
                className={`rounded px-2.5 py-1 capitalize ${role === r ? 'bg-secondary text-foreground' : 'text-muted-foreground'}`}
              >
                {r}
              </button>
            ))}
          </div>
          <span
            className={`size-2 rounded-full ${live.connected ? 'bg-emerald-400' : 'bg-red-400'}`}
            title={live.connected ? 'live feed connected' : 'live feed disconnected'}
          />
        </div>
      </header>
      <div className="relative flex min-h-0 flex-1">
        {tab === 'map' ? (
          <>
            <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto border-r bg-sidebar p-4">
              <LayerPanel
                layers={layers}
                onToggle={(k: LayerKey, on: boolean) => setLayers((l) => ({ ...l, [k]: on }))}
                particleSpeed={particleSpeed}
                onParticleSpeed={setParticleSpeed}
              />
              <Separator />
              <div className="space-y-3">
                <h2 className="text-sm font-semibold">Routing</h2>
                <RouteCard
                  active={active}
                  pending={pending}
                  hitl={live.hitl}
                  onAutopilot={setAutopilot}
                />
              </div>
              <Separator />
              <div className="space-y-2">
                <h2 className="text-sm font-semibold">Drift replay</h2>
                <p className="text-xs text-muted-foreground">
                  Debris parcels from the hotspot cells, drifting through the mission window of real
                  NOAA daily currents.
                </p>
                <Button
                  size="sm"
                  variant={replayOpen ? 'default' : 'secondary'}
                  className="w-full"
                  onClick={() => {
                    setReplayOpen(!replayOpen)
                    replay.setPlaying(!replayOpen)
                  }}
                >
                  <History /> {replayOpen ? 'Back to live' : 'Open time slider'}
                </Button>
              </div>
              {hotspots && (
                <>
                  <Separator />
                  <p className="text-xs text-muted-foreground">
                    Hotspot cells hold {hotspots.validation.median_ratio.toFixed(1)}× the median
                    measured microplastics of other cells (NOAA NCEI,{' '}
                    {hotspots.validation.n_convergent} vs {hotspots.validation.n_rest} samples).
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
                replay={replay.data && { data: replay.data, frame: replay.frame }}
                modify={
                  mod && {
                    moves: mod.moves,
                    onMove: (id: string, to: LatLon) =>
                      setModifying({ ...mod, moves: { ...mod.moves, [id]: to } }),
                  }
                }
              />
              <div className="pointer-events-none absolute inset-x-0 top-4 z-[1000] flex justify-center">
                <div className="pointer-events-auto">
                  {replay.data ? (
                    <ReplayBar
                      replay={replay.data}
                      frame={replay.frame}
                      playing={replay.playing}
                      onFrame={(f) => {
                        replay.setPlaying(false)
                        replay.setFrame(f)
                      }}
                      onPlaying={replay.setPlaying}
                      onClose={() => setReplayOpen(false)}
                    />
                  ) : (
                    <ClockBar
                      clock={live.clock}
                      simNow={simNow}
                      simStart={config?.sim_start ?? null}
                      onControl={control}
                    />
                  )}
                </div>
              </div>
              {mod && pending && live.hitl && (
                <div className="pointer-events-none absolute inset-x-0 top-24 z-[1000] flex justify-center">
                  <ModifyBar
                    hitl={live.hitl}
                    moved={Object.keys(mod.moves).length}
                    onConfirm={() => confirmModify(mod.routeId, mod.moves)}
                    onExtend={() => extend(mod.routeId)}
                    onCancel={() => setModifying(null)}
                  />
                </div>
              )}
              <div className="absolute bottom-4 left-4 z-[1000]">
                <TelemetryPanel vessel={live.vessel} patches={live.patches} link={link} />
              </div>
            </main>
          </>
        ) : (
          <main className="flex-1 overflow-y-auto">
            {tab === 'metrics' ? <MetricsView /> : <AnalyticsView />}
          </main>
        )}
        {showModal && (
          <div className="pointer-events-none absolute inset-0 z-[1100] flex items-center justify-center bg-background/30">
            <HitlModal
              pending={pending}
              active={active}
              hitl={live.hitl!}
              onDecide={(action) => decide(pending.route_id, action)}
              onModify={() => startModify(pending.route_id)}
            />
          </div>
        )}
        <div className="absolute top-4 right-4 z-[1200]">
          <Toasts alerts={live.alerts} onDismiss={dismiss} />
        </div>
      </div>
    </div>
  )
}
