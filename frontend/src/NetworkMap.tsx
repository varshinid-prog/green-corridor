import { useMemo } from 'react'
import type { Edge, Snapshot } from './types'

type Props = { edges: Edge[]; snapshot: Snapshot | null; route?: string[]; compact?: boolean }
export default function NetworkMap({ edges, snapshot, route = [], compact = false }: Props) {
  const box = useMemo(() => {
    const pts = edges.flatMap(e => e.shape)
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1])
    return { minX: Math.min(...xs, 0), maxX: Math.max(...xs, 400), minY: Math.min(...ys, 0), maxY: Math.max(...ys, 400) }
  }, [edges])
  const project = (x: number, y: number) => ({ x: 48 + (x - box.minX) / (box.maxX - box.minX || 1) * 604, y: 34 + (box.maxY - y) / (box.maxY - box.minY || 1) * 388 })
  const selected = new Set(route)
  return <div className={`network-frame ${compact ? 'network-compact' : ''}`}>
    {!edges.length && <div className="map-loading"><span className="pulse-dot"/>Loading SUMO road network</div>}
    <svg viewBox="0 0 700 465" role="img" aria-label="Live SUMO traffic network">
      <defs><pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#25322e" strokeWidth=".5" opacity=".5"/></pattern><filter id="glow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <rect width="700" height="465" fill="url(#grid)"/>
      {edges.map(edge => { const pts = edge.shape.map(([x,y]) => project(x,y)); const d = pts.map((p,i)=>`${i?'L':'M'}${p.x},${p.y}`).join(' '); return <g key={edge.id}><path d={d} fill="none" stroke="#17241f" strokeWidth="12" strokeLinecap="round"/><path d={d} fill="none" stroke={selected.has(edge.id)?'#20d69c':'#33413c'} strokeWidth={selected.has(edge.id)?3.6:2} strokeLinecap="round" strokeDasharray={selected.has(edge.id)?'8 5':undefined} className={selected.has(edge.id)?'route-line':''}/></g> })}
      {snapshot?.signals.map(signal => { const p=project(signal.x,signal.y); const priority=signal.mode==='PRIORITY'; const lamp=/[Gg]/.test(signal.state)?'#31d59a':/[yY]/.test(signal.state)?'#efb85c':'#ed685b'; return <g key={signal.id} transform={`translate(${p.x} ${p.y})`}><circle r="11" fill="#101916" stroke={priority?'#ec6b56':'#596a63'} strokeWidth="1.5"/><circle r="4" fill={lamp} filter={priority?'url(#glow)':undefined}/><text x="13" y="4" className="map-label">{signal.id}</text></g> })}
      {snapshot?.vehicles.map(v => { const p=project(v.x,v.y); return <g key={v.id} transform={`translate(${p.x} ${p.y})`} className={v.emergency?'ambulance-marker':''}><circle r={v.emergency?10:3.4} fill={v.emergency?'#ed6256':'#8b9b94'} opacity={v.emergency?'.2':'.8'}/><circle r={v.emergency?5:2.1} fill={v.emergency?'#ff675b':'#a3b1aa'}>{v.emergency&&<animate attributeName="r" values="5;8;5" dur="1.4s" repeatCount="indefinite"/>}</circle></g> })}
      <g transform="translate(50 435)"><circle r="4" fill="#a3b1aa"/><text x="12" y="4" className="map-legend">CIVILIAN</text><circle cx="100" r="5" fill="#ff675b"/><text x="112" y="4" className="map-legend">AMBULANCE</text><circle cx="225" r="4" fill="#31d59a"/><text x="237" y="4" className="map-legend">PRIORITY ROUTE</text></g>
    </svg>
    <div className="map-coordinates"><span>SUMO SIMULATION SPACE</span><span>GRID 03 × 03</span></div>
  </div>
}
