export type PatchStatus =
  | 'UNVERIFIED_ANOMALY'
  | 'CONFIRMED_PATCH'
  | 'INTERCEPT_ASSIGNED'
  | 'CLEARED';

export type VesselStatus =
  | 'IDLE'
  | 'EN_ROUTE'
  | 'HARVESTING'
  | 'MAINTENANCE';

export type UserRole = 'FLEET_ADMIN' | 'VESSEL_CAPTAIN';

export interface DebrisPatch {
  id: string;
  h3Index: string;
  latitude: number;
  longitude: number;
  estimatedMassKg: number;
  polymerDensityKgKm2: number;
  confidenceScore: number;
  status: PatchStatus;
  currentVelocityMs?: number;
  currentDirectionDeg?: number;
  predictedLat6h?: number;
  predictedLon6h?: number;
  lastObservedAt: string;
}

export interface Vessel {
  id: string;
  name: string;
  callsign: string;
  operatorId?: string;
  status: VesselStatus;
  latitude: number;
  longitude: number;
  h3Index: string;
  maxCapacityTons: number;
  currentLoadTons: number;
  fuelLevelPct: number;
  cruiseSpeedKnots: number;
  updatedAt: string;
}

export interface RouteWaypoint {
  patchId?: string;
  h3Index: string;
  targetLatitude: number;
  targetLongitude: number;
  estimatedMassKg?: number;
  distanceNm: number;
  estimatedFuelLiters: number;
  completed?: boolean;
  completedAt?: string;
}

export interface InterceptionRoute {
  id: string;
  vesselId: string;
  status: 'PLANNED' | 'ACTIVE' | 'COMPLETED' | 'ABORTED';
  totalDistanceNm: number;
  estimatedFuelLiters: number;
  expectedYieldKg: number;
  waypointsJson: RouteWaypoint[];
  createdAt: string;
}

export interface CurrentGridPoint {
  lat: number;
  lon: number;
  u_ms: number;
  v_ms: number;
  velocity_ms: number;
  direction_deg: number;
  wave_height_m: number;
}

export interface SparkHotspotCluster {
  cluster_id: number;
  center_latitude: number;
  center_longitude: number;
  h3_index_res6: string;
  avg_polymer_density_kg_km2: number;
  estimated_plastic_tonnage: number;
  telemetry_observations: number;
}

export interface SsePipelineEvent {
  timestamp: string;
  stage: 'KAFKA_INGEST' | 'BAYESIAN_FUSION' | 'OPEN_METEO_DRIFT' | 'SPARK_BATCH' | 'ORTOOLS_ROUTE';
  level: 'INFO' | 'WARN' | 'SUCCESS';
  message: string;
  payload?: any;
}

export interface LayerVisibilityState {
  h3Debris: boolean;
  currentParticles: boolean;
  driftCones: boolean;
  vesselRoutes: boolean;
  sparkHotspots: boolean;
  stormHazard: boolean;
  pitch3D: boolean;
}

