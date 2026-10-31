import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import { CanvasPane } from './CanvasPane'

const fmtLat = (v: number) => `${Math.abs(v)}°${v >= 0 ? 'N' : 'S'}`
const fmtLon = (v: number) => {
  const w = ((v + 540) % 360) - 180
  return `${Math.abs(w)}°${w >= 0 ? 'E' : 'W'}`
}

/** Lat/lon grid with edge labels; the step follows the zoom. Under the land polygons. */
export function GraticuleLayer() {
  const map = useMap()
  useEffect(() => {
    const draw = () => {
      const { ctx } = pane
      pane.clear()
      const z = map.getZoom()
      const step = z < 4 ? 10 : z < 6 ? 5 : z < 8 ? 1 : 0.5
      const b = map.getBounds()
      const lat0 = Math.ceil(Math.max(-80, b.getSouth()) / step) * step
      const lon0 = Math.ceil(b.getWest() / step) * step
      ctx.strokeStyle = 'rgba(160,190,220,0.08)'
      ctx.fillStyle = 'rgba(160,190,220,0.45)'
      ctx.font = '10px "Geist Variable", sans-serif'
      ctx.lineWidth = 1
      ctx.beginPath()
      for (let lat = lat0; lat <= Math.min(80, b.getNorth()); lat += step) {
        const y = Math.round(map.latLngToContainerPoint([lat, b.getWest()]).y) + 0.5
        ctx.moveTo(0, y)
        ctx.lineTo(pane.width, y)
        ctx.fillText(fmtLat(+lat.toFixed(1)), 6, y - 3)
      }
      for (let lon = lon0; lon <= b.getEast(); lon += step) {
        const x = Math.round(map.latLngToContainerPoint([b.getCenter().lat, lon]).x) + 0.5
        ctx.moveTo(x, 0)
        ctx.lineTo(x, pane.height)
        ctx.fillText(fmtLon(+lon.toFixed(1)), x + 3, pane.height - 6)
      }
      ctx.stroke()
    }
    const pane = new CanvasPane(map, 'graticule', 310, draw)
    pane.reset()
    return () => pane.remove()
  }, [map])
  return null
}
