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
  decided_by: 'operator' | 'autopilot' | 'timeout' | null
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
  hitl_hold: boolean // held while a proposal awaits the operator
  reported_at: string
}

/** Human-in-the-loop state from the API hub; `deadline` is wall-clock time while held. */
export interface Hitl {
  autopilot: boolean
  timeout_s: number
  deadline: string | null
}

export interface Alert {
  kind: 'proposal' | 'active' | 'collected' | 'expired' | 'fuel_anomaly' | 'error'
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

export type QueryName = 'telemetry' | 'debris_survey' | 'windows'

export interface MetricPoint {
  t: string // wall time, bucket start
  query: QueryName
  rows_per_s: number
  duration_ms: number | null
  kafka_lag: number | null
}

export interface QueryProgress {
  ts: string
  query: QueryName
  batch_id: number
  input_rows: number
  input_rps: number | null
  processed_rps: number | null
  duration_ms: number | null
  kafka_lag: number | null
}

export interface HourWindow {
  hour: string // sim time
  energy_kwh: number
  collected_kg: number
  fuel_l: number
  battery_pct: number
  anomalies: number
}

export interface Metrics {
  bucket_s: number
  series: MetricPoint[]
  latest: QueryProgress[]
  lake: { dataset: string; rows: number; updated_at: string }[]
  hourly: HourWindow[]
  alerts: StoredAlert[] // newest first
}

/** A row of the `alerts` table (stream-raised, e.g. fuel_anomaly); `ts` is sim time. */
export interface StoredAlert {
  alert_id: number
  ts: string
  kind: string
  level: 'info' | 'success' | 'warn'
  text: string
}

export interface Yield {
  rows: number
  energy_kwh: number
  collected_kg: number
  kg_per_kwh: number | null
}

export interface Analytics {
  telemetry: {
    computed_at: string
    daily: (Yield & { date: string })[]
    zones: (Yield & { zone: string })[]
  } | null
  decisions: { by: 'operator' | 'autopilot' | 'timeout'; status: RouteStatus; n: number }[]
  acceptance: { operator: number | null; autopilot: number | null; overall: number | null }
  validation: { median_ratio: number; n_convergent: number; n_rest: number } | null
}

/** Time-slider replay: parcels drifting through the mission window's real daily currents. */
export interface Replay {
  step_s: number
  frames: { t: string; data_t: string }[] // t: sim time (for /currents/grid), data_t: real day
  parcels: { id: string; track: LatLon[] }[]
}
