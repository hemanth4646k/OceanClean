import { useEffect } from 'react'
import type { LiveState } from '@/lib/useLive'

const TONE = {
  info: 'border-cyan-400/40',
  success: 'border-emerald-400/40',
  warn: 'border-amber-400/50',
}

type Item = LiveState['alerts'][number]

function Toast({ alert, onDismiss }: { alert: Item; onDismiss: (id: number) => void }) {
  // Warnings (fuel anomaly, expired proposal) stay until clicked: at fast sim rates they would
  // otherwise come and go before anyone looks.
  const sticky = alert.level === 'warn'
  useEffect(() => {
    if (sticky) return
    const t = setTimeout(() => onDismiss(alert.id), 6000)
    return () => clearTimeout(t)
  }, [alert.id, onDismiss, sticky])
  return (
    <button
      onClick={() => onDismiss(alert.id)}
      className={`rounded-lg border bg-card/95 px-3 py-2 text-left text-sm shadow-lg backdrop-blur ${TONE[alert.level]}`}
    >
      {alert.text}
      {sticky && <span className="block text-xs text-muted-foreground">click to dismiss</span>}
    </button>
  )
}

/** Alerts from the /ws feed (proposals, accepted routes, collections) and failed actions. */
export function Toasts({ alerts, onDismiss }: { alerts: Item[]; onDismiss: (id: number) => void }) {
  return (
    <div className="flex w-80 flex-col gap-2">
      {alerts.map((a) => (
        <Toast key={a.id} alert={a} onDismiss={onDismiss} />
      ))}
    </div>
  )
}
