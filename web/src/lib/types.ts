// JSON shapes served by api/ (store.py, api_app.py). Timestamps are ISO-8601 UTC strings.

export type LatLon = [number, number]

export interface Box {
  lat_min: number
  lat_max: number
  lon_min: number
  lon_max: number
}

export interface Config {
  vessel_id: string
  sim_start: string
  mission_box: Box
  history_box: Box
}

export interface Vessel {
  vessel_id: string
  event_ts: string
  seq: number
  lat: number
  lon: number
  heading_deg: number
  speed_kn: number
  battery_pct: number
  fuel_l: number
  debris_density: number
  hold_fill_pct: number
  buffered: boolean
}

export interface Patch {
  patch_id: string
  survey_ts: string
  lat: number
  lon: number
  mass_kg: number
  radius_m: number
}

export interface Point {
  lat: number
  lon: number
  ts: string
}

export interface Waypoint extends Point {
  kind: 'start' | 'target'
  patch_id?: string
}

export interface Target {
  patch_id: string
  mass_kg: number
  radius_m: number
  now: Point
  predicted: Point // the ghost
  heading_deg: number
  transit_h: number
  dwell_h: number
  energy_kwh: number
  score_kg_per_kwh: number
  drift: LatLon[] // survey position -> intercept point
}

export type RouteStatus = 'pending' | 'active' | 'rejected' | 'expired' | 'superseded'

export interface Route {
  route_id: number
  vessel_id: string
  status: RouteStatus
  reason: string
  planned_at: string
  created_at: string
  decided_at: string | null
  energy_kwh: number
  mass_kg: number
  compute_ms: number
  waypoints: Waypoint[]
  targets: Target[]
}

export interface Routes {
  active: Route | null
  pending: Route | null
}

export interface Clock {
  vessel_id: string
  sim_now: string
  rate: number
  paused: boolean
  reported_at: string
}

export interface Alert {
  kind: 'proposal' | 'active' | 'collected' | 'error'
  level: 'info' | 'success' | 'warn'
  text: string
  ts: string | null
}

export interface Hotspot {
  rank: number
  lat: number
  lon: number
  mean_div: number
  frac_convergent: number
  n_days: number
  mp_n: number
  mp_median: number | null
}

export interface Hotspots {
  cell_deg: number
  validation: { median_ratio: number; n_convergent: number; n_rest: number }
  hotspots: Hotspot[]
}

/** u/v in m/s, rows = lat ascending, columns = lon ascending. */
export interface Grid {
  t: string
  lat: number[]
  lon: number[]
  u: number[][]
  v: number[][]
}
