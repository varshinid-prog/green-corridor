import { useMemo, useState } from 'react'
import { Activity, ArrowRight, ChevronDown, Clock3, Hospital, Map as MapIcon, Navigation, RefreshCw, Route as RouteIcon } from 'lucide-react'
import { api } from './api'
import NetworkMap from './NetworkMap'
import type { Edge, RoutePreview, Snapshot } from './types'
import './route-page.css'

type Props = {
  snapshot: Snapshot | null
  edges: Edge[]
  edgeIds: string[]
  origin: string
  setOrigin: (value: string) => void
  destination: string
  setDestination: (value: string) => void
  reroute: () => Promise<void>
}

export default function RoutePage({ snapshot, edges, edgeIds, origin, setOrigin, destination, setDestination, reroute }: Props) {
  const [preview, setPreview] = useState<RoutePreview | null>(null)
  const [error, setError] = useState('')
  const trip = snapshot?.emergency
  const activeTrip = trip && ['QUEUED', 'EN_ROUTE', 'PRIORITY'].includes(trip.status) ? trip : null
  const route = preview?.route ?? activeTrip?.route ?? []
  const edgeById = useMemo(() => new Map(edges.map(edge => [edge.id, edge])), [edges])
  const distance = preview?.distance ?? route.reduce((sum, id) => sum + (edgeById.get(id)?.length ?? 0), 0)
  const calculate = async () => {
    setError('')
    try { setPreview(await api.previewRoute({ origin, destination })) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Route calculation failed') }
  }
  const updateOrigin = (value: string) => { setOrigin(value); setPreview(null) }
  const updateDestination = (value: string) => { setDestination(value); setPreview(null) }

  return <div className="route-page">
    <section className="panel route-control">
      <div className="route-select-group">
        <label className="field"><span>ORIGIN EDGE</span><div className="select-wrap"><Navigation size={14}/><select value={origin} onChange={event => updateOrigin(event.target.value)}><option value="">Select origin</option>{edgeIds.map(id => <option key={id}>{id}</option>)}</select><ChevronDown size={14}/></div></label>
        <ArrowRight className="route-arrow" size={16}/>
        <label className="field"><span>DESTINATION EDGE</span><div className="select-wrap"><Hospital size={14}/><select value={destination} onChange={event => updateDestination(event.target.value)}><option value="">Select destination</option>{edgeIds.map(id => <option key={id}>{id}</option>)}</select><ChevronDown size={14}/></div></label>
        <button className="btn btn-primary" onClick={() => void calculate()} disabled={!origin || !destination}><RouteIcon size={14}/> Calculate route</button>
        {activeTrip && <button className="btn btn-ghost" onClick={() => void reroute()}><RefreshCw size={13}/> Reroute ambulance</button>}
      </div>
      <div className="route-method"><span className="method-tag"><Activity size={12}/> {preview?.traffic_aware ? 'TRAFFIC AWARE' : 'NETWORK ROUTE'}</span><span>Directed SUMO road graph · Live edge speeds and vehicle counts are used while the simulation runs</span></div>
      {error && <div className="inline-hint">{error}</div>}
    </section>
    <div className="route-grid">
      <section className="panel route-map-panel"><div className="panel-header"><div><div className="panel-title"><span className="panel-title-icon"><MapIcon size={15}/></span> Route overview</div><div className="panel-subtitle">{preview ? `${origin} to ${destination} · preview` : activeTrip ? `${activeTrip.origin} to ${activeTrip.destination}` : 'Choose road edges and calculate a route'}</div></div>{activeTrip && !preview && <span className="severity high">{activeTrip.severity} RESPONSE</span>}</div><NetworkMap edges={edges} snapshot={snapshot} route={route}/></section>
      <section className="panel route-detail"><div className="panel-header"><div><div className="panel-title"><span className="panel-title-icon mint-icon"><RouteIcon size={15}/></span> Route segments</div><div className="panel-subtitle">Ordered SUMO road edges</div></div></div>
        {route.length ? <><div className="route-kpis"><div><span>SEGMENTS</span><b>{route.length}</b></div><div><span>ROUTE LENGTH</span><b>{Math.round(distance)} <small>m</small></b></div><div><span>STATUS</span><b className="route-status">{preview ? 'PREVIEW' : activeTrip?.status.replace('_', ' ') ?? 'ROUTE'}</b></div></div>{preview && <div className="route-eta"><Clock3 size={12}/> Estimated travel cost <b>{preview.estimated_seconds}s</b></div>}<div className="segment-list">{route.map((id, index) => <div className="segment" key={`${id}-${index}`}><span className="segment-index">{String(index + 1).padStart(2, '0')}</span><span className="segment-line"><i/></span><div className="segment-name"><b>{id}</b><small>{index === 0 ? 'Origin road' : index === route.length - 1 ? 'Destination road' : 'Connecting road'}</small></div><span className="segment-length">{Math.round(edgeById.get(id)?.length ?? 0)} m</span></div>)}</div></> : <div className="route-empty"><RouteIcon size={22}/><strong>No route calculated</strong><span>Select an origin and destination, then calculate a route preview.</span></div>}
      </section>
    </div>
  </div>
}
