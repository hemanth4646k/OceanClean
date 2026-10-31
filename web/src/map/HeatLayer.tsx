import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import type { Patch } from '@/lib/types'
import { CanvasPane } from './CanvasPane'

const GLOW_M = 90_000 // glow radius around a patch centre, metres: the debris field around it

/** Debris heatmap: an additive glow per live patch, stronger for heavier patches. */
export function HeatLayer({ patches }: { patches: Patch[] }) {
  const map = useMap()
  const paneRef = useRef<CanvasPane | null>(null)
  const patchesRef = useRef(patches)

  useEffect(() => {
    const draw = () => {
      const pane = paneRef.current
      if (!pane) return
      const { ctx } = pane
      pane.clear()
      const live = patchesRef.current.filter((p) => p.mass_kg > 0)
      const max = Math.max(1, ...live.map((p) => p.mass_kg))
      ctx.globalCompositeOperation = 'lighter'
      for (const p of live) {
        const c = map.latLngToContainerPoint([p.lat, p.lon])
        const edge = map.latLngToContainerPoint([p.lat + GLOW_M / 111_320, p.lon])
        const r = Math.max(30, c.y - edge.y)
        const a = 0.1 + 0.3 * Math.sqrt(p.mass_kg / max)
        const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, r)
        grad.addColorStop(0, `rgba(255,140,50,${a})`)
        grad.addColorStop(0.45, `rgba(240,80,30,${a * 0.55})`)
        grad.addColorStop(1, 'rgba(200,40,20,0)')
        ctx.fillStyle = grad
        ctx.fillRect(c.x - r, c.y - r, 2 * r, 2 * r)
      }
      ctx.globalCompositeOperation = 'source-over'
    }
    paneRef.current = new CanvasPane(map, 'heat', 330, draw)
    paneRef.current.reset()
    return () => {
      paneRef.current?.remove()
      paneRef.current = null
    }
  }, [map])

  useEffect(() => {
    patchesRef.current = patches
    paneRef.current?.reset()
  }, [patches])

  return null
}
