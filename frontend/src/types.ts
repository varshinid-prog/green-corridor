export type Edge = { id: string; from: string; to: string; length: number; speed: number; shape: [number, number][] }
export type Vehicle = { id: string; x: number; y: number; speed: number; edge: string; emergency: boolean }
export type Signal = { id: string; x: number; y: number; state: string; mode: string }
export type Trip = { id: string; vehicle_id: string; origin: string; destination: string; severity: string; status: string; route: string[]; created_at: number; travel_time?: number; distance: number }
export type EventItem = { id: string; time: number; type: string; data: Record<string, unknown> }
export type Snapshot = { status: string; step: number; time: number; vehicles: Vehicle[]; signals: Signal[]; emergency: Trip | null; signal_controller: { active_intersection: string | null; stage: string }; metrics: { vehicles: number; ambulance: number; mean_speed: number; junctions: number; priority_passages: number; completed_trips: number }; error?: string | null }
export type Analytics = { completed_trips: number; average_travel_time: number | null; priority_success_rate: number | null; priority_passages: number; event_count: number; sampled_vehicle_wait: number | null; journey_times: { trip: string; seconds: number }[]; note: string }
export type RoutePreview = { route: string[]; distance: number; estimated_seconds: number; traffic_aware: boolean }
