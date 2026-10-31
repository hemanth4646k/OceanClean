import type { Grid } from '@/lib/types'

/** Bilinear (u, v) in m/s at a position on a regular ascending grid; null off the grid. */
export function sampleGrid(g: Grid, lat: number, lon: number): [number, number] | null {
  const nLat = g.lat.length
  const nLon = g.lon.length
  if (nLat < 2 || nLon < 2) return null
  const fi = (lat - g.lat[0]) / (g.lat[1] - g.lat[0])
  const fj = (lon - g.lon[0]) / (g.lon[1] - g.lon[0])
  if (fi < 0 || fj < 0 || fi > nLat - 1 || fj > nLon - 1) return null
  const i = Math.min(Math.floor(fi), nLat - 2)
  const j = Math.min(Math.floor(fj), nLon - 2)
  const wi = fi - i
  const wj = fj - j
  const bl = (a: number[][]): number =>
    (a[i][j] * (1 - wj) + a[i][j + 1] * wj) * (1 - wi) +
    (a[i + 1][j] * (1 - wj) + a[i + 1][j + 1] * wj) * wi
  return [bl(g.u), bl(g.v)]
}
