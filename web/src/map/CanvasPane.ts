import L from 'leaflet'

/**
 * A viewport-sized canvas in its own map pane. Leaflet moves the pane while panning; after each
 * move or zoom the canvas is realigned with the viewport and `onReset` redraws it. Hidden during
 * zoom animations (leaflet-zoom-hide).
 */
export class CanvasPane {
  readonly canvas: HTMLCanvasElement
  readonly ctx: CanvasRenderingContext2D
  private readonly map: L.Map
  private readonly onReset: () => void

  constructor(map: L.Map, name: string, zIndex: number, onReset: () => void) {
    this.map = map
    this.onReset = onReset
    const pane = map.getPane(name) ?? map.createPane(name)
    pane.style.zIndex = String(zIndex)
    pane.style.pointerEvents = 'none'
    this.canvas = L.DomUtil.create('canvas', 'leaflet-zoom-hide', pane)
    this.ctx = this.canvas.getContext('2d')!
    map.on('moveend zoomend resize', this.reset)
  }

  get width(): number {
    return this.map.getSize().x
  }

  get height(): number {
    return this.map.getSize().y
  }

  reset = (): void => {
    const size = this.map.getSize()
    const dpr = window.devicePixelRatio || 1
    this.canvas.width = size.x * dpr
    this.canvas.height = size.y * dpr
    this.canvas.style.width = `${size.x}px`
    this.canvas.style.height = `${size.y}px`
    L.DomUtil.setPosition(this.canvas, this.map.containerPointToLayerPoint([0, 0]))
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    this.onReset()
  }

  clear(): void {
    this.ctx.clearRect(0, 0, this.width, this.height)
  }

  remove(): void {
    this.map.off('moveend zoomend resize', this.reset)
    this.canvas.remove()
  }
}
