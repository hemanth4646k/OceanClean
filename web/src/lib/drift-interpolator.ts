import { latLngToCell } from 'h3-js';
import { DebrisPatch, Vessel, InterceptionRoute } from '../types/marine';

export interface InterpolatedPatch extends DebrisPatch {
  currentLat: number;
  currentLon: number;
  currentH3: string;
}

export interface InterpolatedVessel extends Vessel {
  currentLat: number;
  currentLon: number;
  currentHeadingDeg: number;
}

/**
 * Linearly interpolates a patch's position between T+0h and T+24h
 * based on its 6h drift coordinates and current velocity vectors.
 */
export function interpolatePatchPosition(
  patch: DebrisPatch,
  targetHour: number,
): { lat: number; lon: number; h3: string } {
  const originLat = patch.latitude;
  const originLon = patch.longitude;

  // 6h predicted coordinates (or compute from velocity if missing)
  const dLon6h = patch.predictedLon6h !== undefined ? (patch.predictedLon6h - originLon) : 0.35;
  const dLat6h = patch.predictedLat6h !== undefined ? (patch.predictedLat6h - originLat) : 0.0;

  // Hourly delta rates
  const latRatePerHour = dLat6h / 6.0;
  const lonRatePerHour = dLon6h / 6.0;

  const currentLat = originLat + latRatePerHour * targetHour;
  const currentLon = originLon + lonRatePerHour * targetHour;

  let currentH3 = patch.h3Index;
  try {
    currentH3 = latLngToCell(currentLat, currentLon, 7);
  } catch {
    // fallback to original H3 if out of bounds
  }

  return {
    lat: currentLat,
    lon: currentLon,
    h3: currentH3,
  };
}

/**
 * Interpolates vessel position along its assigned OR-Tools route waypoints.
 */
export function interpolateVesselPosition(
  vessel: Vessel,
  route: InterceptionRoute | undefined,
  targetHour: number,
): { lat: number; lon: number; headingDeg: number } {
  if (!route || !route.waypointsJson || route.waypointsJson.length === 0) {
    return {
      lat: vessel.latitude,
      lon: vessel.longitude,
      headingDeg: 90.0,
    };
  }

  const speed = vessel.cruiseSpeedKnots || 12.0;
  const distanceTraveled = speed * targetHour; // in nautical miles

  let accumulatedDist = 0;
  let prevLat = vessel.latitude;
  let prevLon = vessel.longitude;

  for (const wp of route.waypointsJson) {
    const legDist = wp.distanceNm || 15.0;
    if (accumulatedDist + legDist >= distanceTraveled) {
      // Vessel is along this leg
      const ratio = Math.max(0, Math.min(1, (distanceTraveled - accumulatedDist) / legDist));
      const lat = prevLat + (wp.targetLatitude - prevLat) * ratio;
      const lon = prevLon + (wp.targetLongitude - prevLon) * ratio;

      // Heading calculation
      const dLon = wp.targetLongitude - prevLon;
      const dLat = wp.targetLatitude - prevLat;
      const headingDeg = (Math.atan2(dLon, dLat) * 180 / Math.PI + 360) % 360;

      return { lat, lon, headingDeg };
    }
    accumulatedDist += legDist;
    prevLat = wp.targetLatitude;
    prevLon = wp.targetLongitude;
  }

  // Vessel reached final waypoint
  const lastWp = route.waypointsJson[route.waypointsJson.length - 1];
  return {
    lat: lastWp.targetLatitude,
    lon: lastWp.targetLongitude,
    headingDeg: 90.0,
  };
}

