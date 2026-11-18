import type { Analytics, Edge, EventItem, RoutePreview, Snapshot, Trip } from './types'

const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`)
  return data as T
}

export const api = {
  network: () => request<{ nodes: { id: string; x: number; y: number }[]; edges: Edge[] }>('/api/network'),
  state: () => request<Snapshot>('/api/simulation/state'),
  start: () => request<{ status: string }>('/api/simulation/start', { method: 'POST' }),
  stop: () => request<{ status: string }>('/api/simulation/stop', { method: 'POST' }),
  edges: () => request<Edge[]>('/api/edges'),
  previewRoute: (body: { origin: string; destination: string }) => request<RoutePreview>('/api/routes/preview', { method: 'POST', body: JSON.stringify(body) }),
  emergencies: () => request<Trip[]>('/api/emergencies'),
  dispatch: (body: { origin: string; destination: string; severity: string }) => request<Trip>('/api/emergencies', { method: 'POST', body: JSON.stringify(body) }),
  reroute: (id: string) => request<Trip>(`/api/emergencies/${id}/reroute`, { method: 'POST' }),
  events: () => request<EventItem[]>('/api/events'),
  analytics: () => request<Analytics>('/api/analytics'),
}

export function connectLive(onSnapshot: (snapshot: Snapshot) => void) {
  const url = BASE.replace(/^http/, 'ws') + '/ws/live'
  const socket = new WebSocket(url)
  socket.onmessage = event => { try { onSnapshot(JSON.parse(event.data) as Snapshot) } catch { /* ignore malformed frame */ } }
  return socket
}
