import type { LatLon, Route } from '@/lib/types'

/** A route with operator-moved target waypoints applied (Modify preview). */
export function withMoves(route: Route, moves: Record<string, LatLon>): Route {
  return {
    ...route,
    waypoints: route.waypoints.map((w) => {
      const m = w.patch_id ? moves[w.patch_id] : undefined
      return m ? { ...w, lat: m[0], lon: m[1] } : w
    }),
  }
}
