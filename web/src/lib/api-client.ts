import {
  DebrisPatch,
  Vessel,
  InterceptionRoute,
  CurrentGridPoint,
  SparkHotspotCluster,
} from '../types/marine';

const API_BASE = '/api/v1';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('ocean_token');
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('ocean_token', token);
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });

      if (!response.ok) {
        throw new Error(`API ${endpoint} failed with HTTP ${response.status}`);
      }

      return (await response.json()) as T;
    } catch (err: any) {
      console.warn(`[ApiClient] Request to ${endpoint} failed (${err.message}). Using fallback data if applicable.`);
      throw err;
    }
  }

  async loginDemo(role: 'FLEET_ADMIN' | 'VESSEL_CAPTAIN' = 'FLEET_ADMIN'): Promise<string> {
    try {
      const email = role === 'FLEET_ADMIN' ? 'commander@oceanclean.org' : 'captain.sarah@oceanclean.org';
      const res = await this.request<{ accessToken: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password: 'Password123!' }),
      });
      this.setToken(res.accessToken);
      return res.accessToken;
    } catch {
      const mockToken = 'mock_jwt_token_demo_mode';
      this.setToken(mockToken);
      return mockToken;
    }
  }

  async getPatches(status?: string): Promise<DebrisPatch[]> {
    try {
      const query = status ? `?status=${status}` : '';
      return await this.request<DebrisPatch[]>(`/debris-patches${query}`);
    } catch {
      return this.getFallbackPatches();
    }
  }

  async getVessels(): Promise<Vessel[]> {
    try {
      return await this.request<Vessel[]>('/vessels');
    } catch {
      return this.getFallbackVessels();
    }
  }

  async getRoutes(): Promise<InterceptionRoute[]> {
    try {
      return await this.request<InterceptionRoute[]>('/trajectories');
    } catch {
      return this.getFallbackRoutes();
    }
  }

  async getCurrentsGrid(): Promise<{ grid_points: CurrentGridPoint[] }> {
    try {
      return await this.request<{ grid_points: CurrentGridPoint[] }>('/trajectories/currents-grid');
    } catch {
      return { grid_points: this.getFallbackCurrents() };
    }
  }

  async getSparkHotspots(): Promise<{ hotspots: SparkHotspotCluster[] }> {
    try {
      return await this.request<{ hotspots: SparkHotspotCluster[] }>('/trajectories/analytics/hotspots');
    } catch {
      return {
        hotspots: [
          {
            cluster_id: 0,
            center_latitude: 29.5,
            center_longitude: -150.5,
            h3_index_res6: '8636abb97ffffff',
            avg_polymer_density_kg_km2: 42.5,
            estimated_plastic_tonnage: 215.4,
            telemetry_observations: 1120,
          },
          {
            cluster_id: 1,
            center_latitude: 33.2,
            center_longitude: -143.8,
            h3_index_res6: '863676597ffffff',
            avg_polymer_density_kg_km2: 51.0,
            estimated_plastic_tonnage: 168.2,
            telemetry_observations: 840,
          },
          {
            cluster_id: 2,
            center_latitude: 35.4,
            center_longitude: -138.2,
            h3_index_res6: '86374b54fffffff',
            avg_polymer_density_kg_km2: 56.8,
            estimated_plastic_tonnage: 124.9,
            telemetry_observations: 490,
          },
        ],
      };
    }
  }

  async generateRoutes(): Promise<InterceptionRoute[]> {
    return this.request<InterceptionRoute[]>('/trajectories/generate', { method: 'POST' });
  }

  async completeWaypoint(routeId: string, h3Index: string): Promise<any> {
    return this.request(`/trajectories/${routeId}/waypoints/${h3Index}/complete`, {
      method: 'PATCH',
    });
  }

  async simulateScenario(scenario: string, centerLat?: number, centerLon?: number): Promise<any> {
    return this.request('/telemetry/simulate-scenario', {
      method: 'POST',
      body: JSON.stringify({ scenario, centerLat, centerLon }),
    });
  }

  private getFallbackVessels(): Vessel[] {
    return [
      {
        id: 'vessel-1',
        name: 'RV Ocean Interceptor',
        callsign: 'OI-101',
        status: 'HARVESTING',
        latitude: 28.5,
        longitude: -146.0,
        h3Index: '8736e3c6bffffff',
        maxCapacityTons: 60.0,
        currentLoadTons: 18.5,
        fuelLevelPct: 84.0,
        cruiseSpeedKnots: 14.0,
        updatedAt: new Date().toISOString(),
      },
      {
        id: 'vessel-2',
        name: 'ASV Pacific Vanguard',
        callsign: 'PV-202',
        status: 'EN_ROUTE',
        latitude: 32.0,
        longitude: -142.5,
        h3Index: '873672275ffffff',
        maxCapacityTons: 40.0,
        currentLoadTons: 6.0,
        fuelLevelPct: 91.0,
        cruiseSpeedKnots: 12.0,
        updatedAt: new Date().toISOString(),
      },
      {
        id: 'vessel-3',
        name: 'RV Gyre Harvester',
        callsign: 'GH-303',
        status: 'IDLE',
        latitude: 30.5,
        longitude: -148.5,
        h3Index: '8736e53a9ffffff',
        maxCapacityTons: 80.0,
        currentLoadTons: 0.0,
        fuelLevelPct: 98.0,
        cruiseSpeedKnots: 13.0,
        updatedAt: new Date().toISOString(),
      },
      {
        id: 'vessel-4',
        name: 'ASV Albatross',
        callsign: 'AL-404',
        status: 'IDLE',
        latitude: 34.0,
        longitude: -144.0,
        h3Index: '873670a83ffffff',
        maxCapacityTons: 25.0,
        currentLoadTons: 0.0,
        fuelLevelPct: 100.0,
        cruiseSpeedKnots: 16.0,
        updatedAt: new Date().toISOString(),
      },
    ];
  }

  private getFallbackPatches(): DebrisPatch[] {
    const list: DebrisPatch[] = [];
    for (let i = 0; i < 18; i++) {
      const lat = 27.5 + (i % 6) * 1.35;
      const lon = -149.0 + Math.floor(i / 6) * 3.4;
      const isConf = i < 11;
      list.push({
        id: `patch-fallback-${i + 1}`,
        h3Index: `87283472${i.toString(16)}ffffff`,
        latitude: lat,
        longitude: lon,
        estimatedMassKg: 3500 + i * 850,
        polymerDensityKgKm2: 30 + i * 5.2,
        confidenceScore: isConf ? 0.88 : 0.62,
        status: isConf ? (i < 3 ? 'INTERCEPT_ASSIGNED' : 'CONFIRMED_PATCH') : 'UNVERIFIED_ANOMALY',
        currentVelocityMs: 1.2,
        currentDirectionDeg: 90.0,
        predictedLat6h: lat,
        predictedLon6h: lon + 0.38,
        lastObservedAt: new Date().toISOString(),
      });
    }
    return list;
  }

  private getFallbackRoutes(): InterceptionRoute[] {
    return [
      {
        id: 'route-demo-1',
        vesselId: 'vessel-1',
        status: 'ACTIVE',
        totalDistanceNm: 58.2,
        estimatedFuelLiters: 780.0,
        expectedYieldKg: 18200.0,
        waypointsJson: [
          {
            patchId: 'patch-fallback-1',
            h3Index: '872834720ffffff',
            targetLatitude: 28.85,
            targetLongitude: -145.62,
            estimatedMassKg: 7500.0,
            distanceNm: 28.5,
            estimatedFuelLiters: 380.0,
            completed: false,
          },
          {
            patchId: 'patch-fallback-2',
            h3Index: '872834721ffffff',
            targetLatitude: 29.8,
            targetLongitude: -145.2,
            estimatedMassKg: 10700.0,
            distanceNm: 29.7,
            estimatedFuelLiters: 400.0,
            completed: false,
          },
        ],
        createdAt: new Date().toISOString(),
      },
    ];
  }

  private getFallbackCurrents(): CurrentGridPoint[] {
    const points: CurrentGridPoint[] = [];
    for (let lat = 26; lat <= 36; lat += 1.5) {
      for (let lon = -152; lon <= -136; lon += 1.5) {
        // Clockwise Gyre Circulation
        const centerLat = 31.0;
        const centerLon = -144.0;
        const dLat = lat - centerLat;
        const dLon = lon - centerLon;
        const angle = Math.atan2(dLat, dLon);
        // Clockwise tangent
        const u = -Math.sin(angle) * 0.8;
        const v = Math.cos(angle) * 0.8;
        const dir = (Math.atan2(u, v) * 180 / Math.PI + 360) % 360;

        points.push({
          lat,
          lon,
          u_ms: round(u, 2),
          v_ms: round(v, 2),
          velocity_ms: round(Math.hypot(u, v), 2),
          direction_deg: round(dir, 1),
          wave_height_m: 1.8,
        });
      }
    }
    return points;
  }
}

function round(val: number, decimals: number): number {
  return Number(val.toFixed(decimals));
}

export const apiClient = new ApiClient();

