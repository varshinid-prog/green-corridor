"""Compatibility launcher for the SUMO simulation outside the web app."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIM = ROOT / "simulation"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Green Corridor SUMO simulation.")
    parser.add_argument("--nogui", action="store_true", help="Run without the SUMO GUI.")
    parser.add_argument("--steps", type=int, default=3000, help="Maximum simulation steps.")
    args = parser.parse_args()
    home = os.environ.get("SUMO_HOME")
    if home:
        sys.path.append(str(Path(home) / "tools"))
    import sumolib
    import traci
    from simulation.signal_controller import SignalController

    config = SIM / "green-corridor.sumocfg"
    network = SIM / "network.net.xml"
    if not config.exists() or not network.exists():
        raise SystemExit("Generated simulation is missing. Run python scripts/setup_simulation.py")
    command = [sumolib.checkBinary("sumo" if args.nogui else "sumo-gui"), "-c", str(config), "--start", "--quit-on-end", "--no-warnings", "--step-length", "0.2"]
    traci.start(command)
    controller = SignalController(api=traci)
    try:
        added = False
        for step in range(args.steps):
            traci.simulationStep()
            if step == 1 and not added:
                traci.vehicle.add("AMBULANCE_01", "ambulanceRoute", typeID="ambulance", depart="now")
                traci.vehicle.setColor("AMBULANCE_01", (0, 80, 255, 255))
                added = True
            controller.update("AMBULANCE_01", traci.simulation.getTime())
            if traci.simulation.getMinExpectedNumber() == 0:
                break
    finally:
        traci.close()


if __name__ == "__main__":
    main()
