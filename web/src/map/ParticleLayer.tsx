import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import type { Grid } from '@/lib/types'
import { CanvasPane } from './CanvasPane'
import { sampleGrid } from './field'

interface Particle {
  x: number
  y: number
  age: number
  life: number
}

const FADE = 0.95 // trail alpha kept per frame
const PX_PER_MPS = 7 // pixels per frame for 1 m/s at speed 1 (visual, not to scale)
// Brighter for faster water; currents here are mostly 0.02-0.2 m/s.
const BANDS = [0.04, 0.08, 0.13, Infinity]
const COLORS = [
  'rgba(125,211,252,0.5)',
  'rgba(165,230,250,0.7)',
  'rgba(210,245,255,0.75)',
  'rgba(255,255,255,0.95)',
]

/** Current particles advected through the u/v grid on a canvas (windy-style trails). */
export function ParticleLayer({ grid, speed }: { grid: Grid; speed: number }) {
  const map = useMap()
  const gridRef = useRef(grid)
  const speedRef = useRef(speed)
  useEffect(() => {
    gridRef.current = grid
    speedRef.current = speed
  }, [grid, speed])

  useEffect(() => {
    let particles: Particle[] = []
    let raf = 0
    let moving = false

    // The part of the viewport (container pixels) that the grid covers.
    const area = () => {
      const g = gridRef.current
      const a = map.latLngToContainerPoint([g.lat[0], g.lon[0]])
      const b = map.latLngToContainerPoint([g.lat[g.lat.length - 1], g.lon[g.lon.length - 1]])
      const size = map.getSize()
      const x0 = Math.max(0, Math.min(a.x, b.x))
      const x1 = Math.min(size.x, Math.max(a.x, b.x))
      const y0 = Math.max(0, Math.min(a.y, b.y))
      const y1 = Math.min(size.y, Math.max(a.y, b.y))
      return x1 > x0 && y1 > y0 ? { x0, x1, y0, y1 } : null
    }
    const spawn = (r: { x0: number; x1: number; y0: number; y1: number }): Particle => ({
      x: r.x0 + Math.random() * (r.x1 - r.x0),
      y: r.y0 + Math.random() * (r.y1 - r.y0),
      age: 0,
      life: 40 + Math.random() * 80,
    })
    const seed = () => {
      pane.clear()
      const r = area()
      if (!r) {
        particles = []
        return
      }
      const n = Math.round(Math.min(4000, Math.max(300, ((r.x1 - r.x0) * (r.y1 - r.y0)) / 220)))
      particles = Array.from({ length: n }, () => {
        const p = spawn(r)
        p.age = Math.random() * p.life
        return p
      })
    }
    const pane = new CanvasPane(map, 'particles', 350, seed)

    const frame = () => {
      raf = requestAnimationFrame(frame)
      if (moving || particles.length === 0) return
      const { ctx } = pane
      const g = gridRef.current
      const k = PX_PER_MPS * speedRef.current
      const r = area()
      ctx.globalCompositeOperation = 'destination-in'
      ctx.fillStyle = `rgba(0,0,0,${FADE})`
      ctx.fillRect(0, 0, pane.width, pane.height)
      ctx.globalCompositeOperation = 'source-over'
      ctx.lineWidth = 1.4
      const paths = BANDS.map(() => new Path2D())
      for (const p of particles) {
        const ll = map.containerPointToLatLng([p.x, p.y])
        const uv = sampleGrid(g, ll.lat, ll.lng)
        if (!uv || ++p.age > p.life) {
          if (r) Object.assign(p, spawn(r))
          continue
        }
        const [u, v] = uv
        const x = p.x + u * k
        const y = p.y - v * k // screen y grows southwards
        const s = Math.hypot(u, v)
        const path = paths[BANDS.findIndex((b) => s < b)]
        path.moveTo(p.x, p.y)
        path.lineTo(x, y)
        p.x = x
        p.y = y
      }
      paths.forEach((path, i) => {
        ctx.strokeStyle = COLORS[i]
        ctx.stroke(path)
      })
    }

    const stop = () => {
      moving = true
      pane.clear()
    }
    const go = () => {
      moving = false
    }
    map.on('movestart zoomstart', stop)
    map.on('moveend', go)
    pane.reset()
    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      map.off('movestart zoomstart', stop)
      map.off('moveend', go)
      pane.remove()
    }
  }, [map])

  return null
}
