"""Safe, route-aware traffic-signal priority for the SUMO demo network."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass
class Priority:
    tls_id: str
    incoming: str
    outgoing: str
    link_indices: Tuple[int, ...]
    stage: str
    started_at: float


class SignalController:
    def __init__(self, api=None, yellow_duration: float = 3.0,
                 all_red_duration: float = 2.0, detection_distance: float = 100.0,
                 emit: Optional[Callable[[str, dict], None]] = None):
        if api is None:
            import traci as api
        self.api = api
        self.yellow_duration = yellow_duration
        self.all_red_duration = all_red_duration
        self.detection_distance = detection_distance
        self.emit = emit or (lambda _name, _data: None)
        self.active: Optional[Priority] = None

    def _start(self, tls_id: str, incoming: str, outgoing: str, index: int, now: float) -> None:
        state = self.api.trafficlight.getRedYellowGreenState(tls_id)
        yellow = "".join("y" if lamp in ("G", "g") else lamp for lamp in state)
        self.active = Priority(tls_id, incoming, outgoing, (index,), "YELLOW", now)
        if any(lamp in ("G", "g") for lamp in state):
            self.api.trafficlight.setRedYellowGreenState(tls_id, yellow)
        else:
            self.api.trafficlight.setRedYellowGreenState(tls_id, "r" * len(state))
            self.active.stage = "ALL_RED"
            self.active.started_at = now
        self.emit("signal.yellow", {"intersection": tls_id, "incoming": incoming, "outgoing": outgoing})

    def _restore(self, reason: str) -> None:
        active = self.active
        if active is None:
            return
        self.api.trafficlight.setProgram(active.tls_id, "0")
        self.emit("signal.restored", {"intersection": active.tls_id, "reason": reason})
        self.active = None

    def update(self, ambulance_id: str, now: float) -> None:
        vehicles = set(self.api.vehicle.getIDList())
        active = self.active
        if active is None:
            if ambulance_id not in vehicles:
                return
            route = self.api.vehicle.getRoute(ambulance_id)
            route_index = self.api.vehicle.getRouteIndex(ambulance_id)
            incoming = self.api.vehicle.getRoadID(ambulance_id)
            for info in self.api.vehicle.getNextTLS(ambulance_id):
                tls_id, link_index, distance, _state = info[:4]
                if distance > self.detection_distance or route_index + 1 >= len(route):
                    continue
                outgoing = route[route_index + 1]
                state = self.api.trafficlight.getRedYellowGreenState(tls_id)
                index = int(link_index)
                if 0 <= index < len(state):
                    self._start(tls_id, incoming, outgoing, index, now)
                    return
            return

        if ambulance_id not in vehicles:
            self._restore("ambulance_missing")
            return
        elapsed = now - active.started_at
        if active.stage == "YELLOW" and elapsed >= self.yellow_duration:
            state = "r" * len(self.api.trafficlight.getRedYellowGreenState(active.tls_id))
            self.api.trafficlight.setRedYellowGreenState(active.tls_id, state)
            active.stage, active.started_at = "ALL_RED", now
            self.emit("signal.all_red", {"intersection": active.tls_id})
        elif active.stage == "ALL_RED" and elapsed >= self.all_red_duration:
            state = ["r"] * len(self.api.trafficlight.getRedYellowGreenState(active.tls_id))
            for index in active.link_indices:
                state[index] = "G"
            self.api.trafficlight.setRedYellowGreenState(active.tls_id, "".join(state))
            active.stage, active.started_at = "EMERGENCY_GREEN", now
            self.emit("signal.priority", {"intersection": active.tls_id})
        elif active.stage == "EMERGENCY_GREEN":
            if self.api.vehicle.getRoadID(ambulance_id) == active.outgoing:
                self._restore("ambulance_passed")

    def snapshot(self) -> dict:
        active = self.active
        return {"active_intersection": active.tls_id if active else None,
                "stage": active.stage if active else "NORMAL"}
