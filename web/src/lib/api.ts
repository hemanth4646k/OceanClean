// REST calls go to /api (nginx or the Vite dev proxy strips the prefix); the feed is /ws.

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`)
  return (await res.json()) as T
}

export async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`)
  return (await res.json()) as T
}

export function wsURL(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

export const ms = (iso: string): number => Date.parse(iso)
