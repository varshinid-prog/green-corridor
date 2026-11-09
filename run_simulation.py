from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIM = ROOT / "simulation"


def configure_sumo_imports() -> None:
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools = str(Path(sumo_home) / "tools")
        if tools not in sys.path:
            sys.path.append(tools)


def find_sumo_binary(gui: bool) -> str:
    import sumolib
    return sumolib.checkBinary("sumo-gui" if gui else "sumo")


def choose_connected_route(net):
    edges = [
        edge for edge in net.getEdges()
        if not edge.getID().startswith(":")
        and edge.getLength() > 80
    ]
    random.seed(7)
    random.shuffle(edges)

    for start in edges:
        for end in edges:
            if start.getID() == end.getID():
                continue
            route = net.getShortestPath(start, end)
            if route and route[0] is not None and len(route[0]) >= 2:
                return [edge.getID() for edge in route[0]]

    raise RuntimeError("Could not find a connected pair of road segments.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Green Corridor Phase 1 SUMO simulation.")
    parser.add_argument("--nogui", action="store_true", help="Run without the SUMO GUI.")
    parser.add_argument("--steps", type=int, default=3000, help="Maximum simulation steps.")
    args = parser.parse_args()

    config = SIM / "green-corridor.sumocfg"
    network_file = SIM / "network.net.xml"
    if not config.exists() or not network_file.exists():
        raise SystemExit("Simulation files are missing. Run: python scripts/setup_simulation.py")

    configure_sumo_imports()
    import traci
    import sumolib

    net = sumolib.net.readNet(str(network_file))
    ambulance_route = choose_connected_route(net)

    binary = find_sumo_binary(gui=not args.nogui)
    command = [
        binary,
        "-c", str(config),
        "--start",
        "--quit-on-end",
        "--no-warnings",
    ]

    print("Starting SUMO...")
    traci.start(command)

    ambulance_added = False
    ambulance_departed = False

    try:
        for step in range(args.steps):
            traci.simulationStep()

            if step == 10 and not ambulance_added:
                traci.route.add("ambulance_route", ambulance_route)
                try:
                    traci.vehicletype.copy("DEFAULT_VEHTYPE", "ambulance")
                except Exception:
                    pass

                traci.vehicle.add(
                    vehID="AMBULANCE_1",
                    routeID="ambulance_route",
                    typeID="ambulance",
                    depart="now",
                )
                traci.vehicle.setColor("AMBULANCE_1", (0, 80, 255, 255))
                ambulance_added = True
                print("Ambulance inserted. Route:", " -> ".join(ambulance_route))

            if ambulance_added and "AMBULANCE_1" in traci.vehicle.getIDList():
                if not ambulance_departed:
                    ambulance_departed = True
                    print("Ambulance is moving.")

                if step % 100 == 0:
                    road = traci.vehicle.getRoadID("AMBULANCE_1")
                    position = traci.vehicle.getPosition("AMBULANCE_1")
                    print(f"t={traci.simulation.getTime():.1f}s | ambulance road={road} | position={position}")

            if ambulance_added and ambulance_departed:
                if "AMBULANCE_1" not in traci.vehicle.getIDList():
                    print("Ambulance journey completed.")
                    break

            if traci.simulation.getMinExpectedNumber() <= 0 and ambulance_added:
                break

    finally:
        traci.close()

    print("Simulation finished.")


if __name__ == "__main__":
    main()
