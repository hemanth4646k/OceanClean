import { useEffect, useReducer } from 'react'
import { ms, wsURL } from './api'
import type { Alert, Clock, Hitl, LatLon, Patch, Routes, Vessel } from './types'

export interface LiveState {
  connected: boolean
  vessel: Vessel | null
  wake: LatLon[]
  patches: Patch[]
  routes: Routes
  clock: Clock | null
  hitl: Hitl | null
  clockAt: number // wall ms when `clock` arrived, to extrapolate sim time
  alerts: (Alert & { id: number })[]
}

type Msg =
  | { type: 'snapshot'; data: Omit<LiveState, 'connected' | 'clockAt' | 'alerts'> }
  | { type: 'vessel'; data: Vessel | null }
  | { type: 'patches'; data: Patch[] }
  | { type: 'routes'; data: Routes }
  | { type: 'clock'; data: Clock | null }
  | { type: 'hitl'; data: Hitl }
  | { type: 'alert'; data: Alert }

type Action =
  | Msg
  | { type: 'connected'; value: boolean }
  | { type: 'dismiss'; id: number }
  | { type: 'local-clock'; data: Clock }
  | { type: 'local-routes'; data: Partial<Routes> }
  | { type: 'local-hitl'; data: Hitl }

const WAKE_MAX = 2000
let alertId = 0

const initial: LiveState = {
  connected: false,
  vessel: null,
  wake: [],
  patches: [],
  routes: { active: null, pending: null },
  clock: null,
  hitl: null,
  clockAt: 0,
  alerts: [],
}

/** The newest 3 warnings (they stay until dismissed) and the newest 4 other alerts. */
function keepAlerts(all: LiveState['alerts']): LiveState['alerts'] {
  const warn = all.filter((x) => x.level === 'warn').slice(-3)
  const rest = all.filter((x) => x.level !== 'warn').slice(-4)
  return [...warn, ...rest].sort((x, y) => x.id - y.id)
}

/** Append the new position; a sim time earlier than the last one is a clean sim start. */
function extendWake(state: LiveState, v: Vessel | null): LatLon[] {
  if (!v) return state.wake
  const prev = state.vessel
  if (prev && ms(v.event_ts) < ms(prev.event_ts)) return [[v.lat, v.lon]]
  if (prev && v.seq === prev.seq) return state.wake
  return [...state.wake, [v.lat, v.lon] as LatLon].slice(-WAKE_MAX)
}

function reduce(state: LiveState, a: Action): LiveState {
  switch (a.type) {
    case 'connected':
      return { ...state, connected: a.value }
    case 'snapshot':
      return { ...state, ...a.data, clockAt: performance.now() }
    case 'vessel':
      return { ...state, vessel: a.data, wake: extendWake(state, a.data) }
    case 'patches':
      return { ...state, patches: a.data }
    case 'routes':
      return { ...state, routes: a.data }
    case 'clock':
    case 'local-clock':
      return { ...state, clock: a.data, clockAt: performance.now() }
    case 'hitl':
    case 'local-hitl':
      return { ...state, hitl: a.data }
    case 'local-routes':
      return { ...state, routes: { ...state.routes, ...a.data } }
    case 'alert':
      return { ...state, alerts: keepAlerts([...state.alerts, { ...a.data, id: ++alertId }]) }
    case 'dismiss':
      return { ...state, alerts: state.alerts.filter((x) => x.id !== a.id) }
  }
}

/** The /ws feed: a full snapshot on connect, then changed parts and alerts. Reconnects. */
export function useLive(): [LiveState, (a: Action) => void] {
  const [state, dispatch] = useReducer(reduce, initial)
  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let closed = false
    const connect = () => {
      ws = new WebSocket(wsURL())
      ws.onopen = () => dispatch({ type: 'connected', value: true })
      ws.onmessage = (e) => dispatch(JSON.parse(e.data as string) as Msg)
      ws.onclose = () => {
        dispatch({ type: 'connected', value: false })
        if (!closed) retry = setTimeout(connect, 2000)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [])
  return [state, dispatch]
}

/** Sim time now, extrapolated from the last clock report at its rate (frozen while paused or
 * held for a decision). */
export function simNowMs(state: LiveState, wallNow: number): number | null {
  const c = state.clock
  if (!c) return null
  const base = ms(c.sim_now)
  return c.paused || c.hitl_hold ? base : base + (wallNow - state.clockAt) * c.rate
}
