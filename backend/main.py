from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "simulation"
DB_PATH = ROOT / "data" / "green_corridor.sqlite3"
DB_PATH.parent.mkdir(exist_ok=True)

app = FastAPI(title="Green Corridor API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)


class DispatchRequest(BaseModel):
    origin: str
    destination: str
    severity: str = Field(default="HIGH", pattern="^(CRITICAL|HIGH|MEDIUM)$")


class RouteRequest(BaseModel):
    origin: str
    destination: str


class SimulationManager:
    """One worker thread owns all TraCI access; HTTP and WS use snapshots."""
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.command_lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.status = "STOPPED"
        self.step = 0
        self.sim_time = 0.0
        self.vehicles: List[dict] = []
        self.signals: List[dict] = []
        self.emergency: Optional[dict] = None
        self.events: deque = deque(maxlen=250)
        self.subscribers: List[asyncio.Queue] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.traci: Any = None
        self.net: Any = None
        self.graph: Any = None
        self.graph_edges: Dict[str, Any] = {}
        self.edge_cost_cache: Dict[str, float] = {}
        self.pending_dispatch: Optional[dict] = None
        self.last_snapshot = 0.0
        self.error: Optional[str] = None
        self.start_wall: Optional[float] = None
        self.metrics = {"completed": 0, "priority_passages": 0, "wait_samples": 0, "wait_total": 0.0, "active_trip_seconds": 0.0}

    def _emit(self, name: str, data: dict) -> None:
        item = {"id": str(uuid.uuid4()), "time": round(self.sim_time, 1), "type": name, "data": data}
        if name == "signal.restored" and data.get("reason") == "ambulance_passed":
            self.metrics["priority_passages"] += 1
        self.events.appendleft(item)
        self._persist("event", item)

    def _persist(self, table: str, value: dict) -> None:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            if table == "event":
                conn.execute("INSERT INTO events (id, time, type, data) VALUES (?, ?, ?, ?)", (value["id"], value["time"], value["type"], json.dumps(value["data"])))
            elif table == "trip":
                conn.execute("INSERT OR REPLACE INTO trips (id, origin, destination, severity, status, route, created_at, completed_at, travel_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (value["id"], value["origin"], value["destination"], value["severity"], value["status"], json.dumps(value["route"]), value["created_at"], value.get("completed_at"), value.get("travel_time")))
            conn.commit()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, time REAL, type TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, origin TEXT, destination TEXT, severity TEXT, status TEXT, route TEXT, created_at REAL, completed_at REAL, travel_time REAL);
            CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, payload TEXT);""")

    def _configure_imports(self) -> None:
        home = os.environ.get("SUMO_HOME")
        if home and str(Path(home) / "tools") not in sys.path:
            sys.path.append(str(Path(home) / "tools"))

    def _load_network(self) -> None:
        import networkx as nx
        import sumolib
        self.net = sumolib.net.readNet(str(SIM / "network.net.xml"))
        self.graph = nx.DiGraph()
        self.graph_edges = {}
        for edge in self.net.getEdges():
            if edge.getID().startswith(":"):
                continue
            edge_id = edge.getID()
            u = edge.getFromNode().getID()
            v = edge.getToNode().getID()
            # Parallel SUMO roads can share a node pair; preserve each edge as a
            # distinct routing state so the API never loses a valid road ID.
            self.graph.add_node("edge:" + edge_id, edge_id=edge_id, edge=edge)
            self.graph.add_edge(u, "edge:" + edge_id, edge_id=edge_id, length=edge.getLength(), free=edge.getSpeed(), edge=edge)
            self.graph.add_edge("edge:" + edge_id, v, edge_id=edge_id, length=0, free=edge.getSpeed(), edge=edge)
            self.graph_edges[edge_id] = edge

    def edges(self) -> List[dict]:
        if self.net is None:
            self._configure_imports()
            self._load_network()
        result = []
        for edge_id, edge in self.graph_edges.items():
            shape = edge.getShape()
            result.append({"id": edge_id, "from": edge.getFromNode().getID(), "to": edge.getToNode().getID(), "length": round(edge.getLength(), 1), "speed": round(edge.getSpeed(), 1), "shape": [[round(x, 1), round(y, 1)] for x, y in shape]})
        return result

    def route(self, origin: str, destination: str, traffic_aware: bool = True) -> List[str]:
        import networkx as nx
        self.edges()
        if origin not in self.graph_edges or destination not in self.graph_edges:
            raise ValueError("Origin or destination is not a valid road edge.")
        start, end = self.graph_edges[origin], self.graph_edges[destination]
        def weight(_u, _v, data):
            edge = data["edge"]
            length = data["length"]
            if length <= 0:
                return 0.0
            free = max(edge.getSpeed(), 1.0)
            if not traffic_aware:
                return length / free
            return self.edge_cost_cache.get(edge.getID(), length / free)
        start_node = "edge:" + origin
        end_node = "edge:" + destination
        path = nx.shortest_path(self.graph, start_node, end_node, weight=weight)
        route = [self.graph.nodes[node]["edge_id"] for node in path if node.startswith("edge:")]
        # The origin road's remaining distance is traversed from the current
        # point; path traversal from its edge-state therefore begins at the next.
        return route or [origin]

    def start(self) -> None:
        with self.lock:
            if self.running:
                return
            if self.thread and self.thread.is_alive():
                raise RuntimeError("Simulation is still shutting down.")
            self._configure_imports()
            self._load_network()
            self.error = None
            self.status = "STARTING"
            self.thread = threading.Thread(target=self._worker, daemon=True, name="sumo-owner")
            self.thread.start()

    def stop(self) -> None:
        with self.lock:
            if not self.running:
                self.status = "STOPPED"
                return
            self.status = "STOPPING"
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=8)

    def dispatch(self, request: DispatchRequest) -> dict:
        with self.command_lock:
            if not self.running or self.status != "RUNNING":
                raise RuntimeError("Start the SUMO simulation before dispatching.")
            if self.emergency and self.emergency["status"] not in ("COMPLETED", "CANCELLED", "FAILED"):
                raise RuntimeError("An emergency trip is already active.")
            route = self.route(request.origin, request.destination)
            trip = {"id": "GC-" + uuid.uuid4().hex[:8].upper(), "vehicle_id": "AMBULANCE_1", "origin": request.origin, "destination": request.destination, "severity": request.severity, "status": "QUEUED", "route": route, "created_at": self.sim_time, "travel_time": None, "distance": 0.0, "vehicle_seen": False}
            with self.lock:
                self.pending_dispatch = trip
                self.emergency = trip
            self._persist("trip", trip)
            self._emit("dispatch.queued", {"trip_id": trip["id"], "origin": trip["origin"], "destination": trip["destination"], "severity": trip["severity"], "route": route})
            return dict(trip)

    def reroute(self, trip_id: str) -> dict:
        with self.command_lock:
            trip = self.emergency
            if not trip or trip["id"] != trip_id or trip["status"] not in ("EN_ROUTE", "PRIORITY"):
                raise RuntimeError("No active trip can be rerouted.")
            route = self.route(trip.get("current_edge") or trip["origin"], trip["destination"])
            with self.lock:
                self.pending_dispatch = dict(trip, route=route, reroute=True)
            self._emit("route.recalculated", {"trip_id": trip_id, "route": route})
            return dict(trip, route=route)

    def _worker(self) -> None:
        self._configure_imports()
        import sumolib
        import traci
        from simulation.signal_controller import SignalController
        binary = sumolib.checkBinary("sumo")
        cfg = SIM / "green-corridor.sumocfg"
        cmd = [binary, "-c", str(cfg), "--start", "--quit-on-end", "--no-warnings", "--step-length", "0.2"]
        try:
            # traci.start chooses an available port; all subsequent calls stay in this thread.
            traci.start(cmd)
            self.traci = traci
            self.signal_controller = SignalController(api=traci, emit=self._emit)
            with self.lock:
                self.running = True
                self.status = "RUNNING"
                self.step = 0
                self.sim_time = 0.0
                self.start_wall = time.time()
            self._emit("simulation.started", {"engine": "SUMO", "network": "3x3", "step_length": 0.2})
            while self.status == "RUNNING":
                traci.simulationStep()
                self.sim_time = float(traci.simulation.getTime())
                self.step += 1
                self._handle_dispatch()
                ambulance = self.emergency
                if ambulance and ambulance["status"] in ("EN_ROUTE", "PRIORITY"):
                    previous = self.signal_controller.snapshot()
                    self.signal_controller.update(ambulance["vehicle_id"], self.sim_time)
                    signal = self.signal_controller.snapshot()
                    if signal["stage"] != previous["stage"] or signal["active_intersection"] != previous["active_intersection"]:
                        if signal["stage"] == "EMERGENCY_GREEN":
                            ambulance["status"] = "PRIORITY"
                            self._persist("trip", ambulance)
                    ambulance_present = ambulance["vehicle_id"] in traci.vehicle.getIDList()
                    if ambulance_present:
                        ambulance["vehicle_seen"] = True
                    if not ambulance_present and ambulance.get("vehicle_seen"):
                        ambulance["status"] = "COMPLETED"
                        ambulance["completed_at"] = self.sim_time
                        ambulance["travel_time"] = round(self.sim_time - ambulance["created_at"], 1)
                        self.metrics["completed"] += 1
                        self.metrics["active_trip_seconds"] += ambulance["travel_time"]
                        self._persist("trip", ambulance)
                        self._emit("trip.completed", {"trip_id": ambulance["id"], "travel_time": ambulance["travel_time"]})
                        self.emergency = ambulance
                if self.step % 2 == 0:
                    self._capture(traci)
                trip_idle = not self.emergency or self.emergency.get("status") in ("COMPLETED", "CANCELLED", "FAILED")
                if traci.simulation.getMinExpectedNumber() <= 0 and trip_idle:
                    traci.load(["-c", str(cfg), "--step-length", "0.2"])
                    self.step = 0
                # Keep simulation time close to wall time so a dispatcher can
                # observe the route and the live UI remains meaningfully live.
                time.sleep(0.2)
        except Exception as exc:
            self.error = str(exc)
            self._emit("simulation.error", {"message": str(exc)})
        finally:
            try:
                traci.close()
            except Exception:
                pass
            with self.lock:
                self.running = False
                self.traci = None
                self.status = "ERROR" if self.error else "STOPPED"
            self._emit("simulation.stopped", {"status": self.status})

    def _handle_dispatch(self) -> None:
        with self.lock:
            command, self.pending_dispatch = self.pending_dispatch, None
        if command is None:
            return
        try:
            ambulance_id = command["vehicle_id"]
            if command.get("reroute"):
                route = command["route"]
                route_id = "route_" + uuid.uuid4().hex[:8]
                self.traci.route.add(route_id, route)
                self.traci.vehicle.setRoute(ambulance_id, route)
                self.emergency["route"] = route
                self._persist("trip", self.emergency)
                return
            route = command["route"]
            route_id = "route_" + uuid.uuid4().hex[:8]
            self.traci.route.add(route_id, route)
            if "ambulance" not in self.traci.vehicletype.getIDList():
                try:
                    self.traci.vehicletype.copy("DEFAULT_VEHTYPE", "ambulance")
                    self.traci.vehicletype.setVehicleClass("ambulance", "emergency")
                    self.traci.vehicletype.setColor("ambulance", (239, 68, 68, 255))
                except Exception:
                    pass
            if ambulance_id in self.traci.vehicle.getIDList():
                raise RuntimeError("Ambulance is already in the simulation.")
            self.traci.vehicle.add(ambulance_id, route_id, typeID="ambulance", depart="now")
            self.traci.vehicle.setColor(ambulance_id, (239, 68, 68, 255))
            command["status"] = "EN_ROUTE"
            self.emergency = command
            self._persist("trip", command)
            self._emit("trip.started", {"trip_id": command["id"], "route": route})
        except Exception as exc:
            command["status"] = "FAILED"
            command["error"] = str(exc)
            self.emergency = command
            self._persist("trip", command)
            self._emit("trip.failed", {"trip_id": command["id"], "message": str(exc)})

    def _capture(self, traci: Any) -> None:
        vehicles = []
        costs = {}
        for vehicle_id in traci.vehicle.getIDList():
            try:
                x, y = traci.vehicle.getPosition(vehicle_id)
                vehicles.append({"id": vehicle_id, "x": round(x, 2), "y": round(y, 2), "speed": round(traci.vehicle.getSpeed(vehicle_id), 2), "edge": traci.vehicle.getRoadID(vehicle_id), "emergency": vehicle_id.startswith("AMBULANCE")})
                if vehicle_id.startswith("AMBULANCE") and self.emergency:
                    self.emergency["distance"] = round(traci.vehicle.getDistance(vehicle_id), 1)
                    try:
                        route = traci.vehicle.getRoute(vehicle_id)
                        route_index = traci.vehicle.getRouteIndex(vehicle_id)
                        self.emergency["current_edge"] = route[route_index]
                    except Exception:
                        self.emergency["current_edge"] = traci.vehicle.getRoadID(vehicle_id)
            except Exception:
                continue
        signals = []
        for tls_id in traci.trafficlight.getIDList():
            try:
                state = traci.trafficlight.getRedYellowGreenState(tls_id)
                signals.append({"id": tls_id, "x": round(self._junction_pos(tls_id)[0], 1), "y": round(self._junction_pos(tls_id)[1], 1), "state": state, "mode": "PRIORITY" if self.signal_controller.snapshot()["active_intersection"] == tls_id else "NORMAL"})
            except Exception:
                continue
        for edge_id, edge in self.graph_edges.items():
            try:
                measured_speed = traci.edge.getLastStepMeanSpeed(edge_id)
                count = traci.edge.getLastStepVehicleNumber(edge_id)
                speed = measured_speed if measured_speed > 0 else max(edge.getSpeed(), 1.0)
                costs[edge_id] = edge.getLength() / speed + count * 1.4
            except Exception:
                costs[edge_id] = edge.getLength() / max(edge.getSpeed(), 1.0)
        with self.lock:
            self.vehicles, self.signals, self.edge_cost_cache = vehicles, signals, costs
        now = time.monotonic()
        if now - self.last_snapshot >= 0.4:
            self.last_snapshot = now
            snapshot = self.snapshot()
            self._broadcast(snapshot)
            self._save_metric(snapshot)

    def _junction_pos(self, tls_id: str):
        junction = self.net.getNode(tls_id)
        return junction.getCoord()

    def _save_metric(self, snapshot: dict) -> None:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO metrics (time, payload) VALUES (?, ?)", (self.sim_time, json.dumps({"vehicles": len(self.vehicles), "mean_speed": snapshot["metrics"]["mean_speed"], "signals": len(self.signals)})))
            conn.commit()

    def _broadcast(self, data: dict) -> None:
        if self.loop and self.subscribers:
            for queue in list(self.subscribers):
                try:
                    self.loop.call_soon_threadsafe(self._queue_put, queue, data)
                except RuntimeError:
                    pass

    @staticmethod
    def _queue_put(queue: asyncio.Queue, data: dict) -> None:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            queue.put_nowait(data)

    def snapshot(self) -> dict:
        with self.lock:
            vehicles = list(self.vehicles)
            signals = list(self.signals)
            emergency = dict(self.emergency) if self.emergency else None
            status, step, sim_time, error = self.status, self.step, self.sim_time, self.error
        speeds = [v["speed"] for v in vehicles if not v["emergency"]]
        metrics = {"vehicles": len([v for v in vehicles if not v["emergency"]]), "ambulance": sum(1 for v in vehicles if v["emergency"]), "mean_speed": round(sum(speeds) / len(speeds), 1) if speeds else 0.0, "junctions": len(signals), "priority_passages": self.metrics["priority_passages"], "completed_trips": self.metrics["completed"]}
        return {"status": status, "step": step, "time": round(sim_time, 1), "vehicles": vehicles, "signals": signals, "emergency": emergency, "signal_controller": getattr(self, "signal_controller", None).snapshot() if getattr(self, "signal_controller", None) else {"active_intersection": None, "stage": "NORMAL"}, "metrics": metrics, "error": error}

    def analytics(self) -> dict:
        import sqlite3
        with sqlite3.connect(DB_PATH) as conn:
            trips = conn.execute("SELECT status, travel_time, severity FROM trips").fetchall()
            event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            passage_events = conn.execute("SELECT data FROM events WHERE type='signal.restored'").fetchall()
        completed = [row[1] for row in trips if row[0] == "COMPLETED" and row[1] is not None]
        successful_passages = sum(1 for (payload,) in passage_events if json.loads(payload).get("reason") == "ambulance_passed")
        return {"completed_trips": len(completed), "average_travel_time": round(sum(completed) / len(completed), 1) if completed else None, "priority_success_rate": round(100 * successful_passages / len(completed), 1) if completed else None, "priority_passages": successful_passages, "event_count": event_count, "sampled_vehicle_wait": None, "journey_times": [{"trip": "GC-" + str(i + 1), "seconds": t} for i, t in enumerate(completed)], "note": "Only measurements recorded by this simulation are shown. Civilian comparison baseline is unavailable until paired runs are recorded."}


manager = SimulationManager()
manager._init_db()


@app.on_event("startup")
async def startup():
    manager.loop = asyncio.get_running_loop()
    manager._configure_imports()
    manager._load_network()


@app.on_event("shutdown")
async def shutdown():
    manager.stop()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "green-corridor-api", "simulation": manager.status}


@app.get("/api/network")
def network():
    return {"nodes": [{"id": n.getID(), "x": round(n.getCoord()[0], 1), "y": round(n.getCoord()[1], 1)} for n in manager.net.getNodes() if n.getType() != "internal"], "edges": manager.edges()}


@app.post("/api/simulation/start")
def start_simulation():
    try:
        manager.start()
        return {"status": manager.status}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/simulation/stop")
def stop_simulation():
    manager.stop()
    return {"status": manager.status}


@app.get("/api/simulation/state")
def simulation_state():
    return manager.snapshot()


@app.get("/api/edges")
def list_edges():
    return manager.edges()


@app.post("/api/routes/preview")
def preview_route(request: RouteRequest):
    try:
        route = manager.route(request.origin, request.destination)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc))
    distance = sum(manager.graph_edges[edge_id].getLength() for edge_id in route)
    estimate = sum(manager.edge_cost_cache.get(edge_id, manager.graph_edges[edge_id].getLength() / max(manager.graph_edges[edge_id].getSpeed(), 1.0)) for edge_id in route)
    return {"route": route, "distance": round(distance, 1), "estimated_seconds": round(estimate, 1), "traffic_aware": manager.status == "RUNNING"}


@app.post("/api/emergencies")
def create_emergency(request: DispatchRequest):
    try:
        return manager.dispatch(request)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/emergencies")
def emergencies():
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM trips ORDER BY created_at DESC LIMIT 50").fetchall()
    return [dict(row, route=json.loads(row["route"])) for row in rows]


@app.get("/api/emergencies/{trip_id}")
def emergency_detail(trip_id: str):
    trip = manager.emergency
    if trip and trip["id"] == trip_id:
        return trip
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Trip not found")
    result = dict(row)
    result["route"] = json.loads(result["route"])
    return result


@app.post("/api/emergencies/{trip_id}/reroute")
def reroute(trip_id: str):
    try:
        return manager.reroute(trip_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/intersections")
def intersections():
    return manager.snapshot()["signals"]


@app.get("/api/analytics")
def analytics():
    return manager.analytics()


@app.get("/api/events")
def events():
    return list(manager.events)


@app.websocket("/ws/live")
async def live(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=3)
    manager.subscribers.append(queue)
    try:
        await websocket.send_json(manager.snapshot())
        while True:
            data = await queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        pass
    finally:
        if queue in manager.subscribers:
            manager.subscribers.remove(queue)
