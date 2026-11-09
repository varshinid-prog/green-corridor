from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "simulation"


def find_tool(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        candidates = [
            Path(sumo_home) / "bin" / name,
            Path(sumo_home) / "bin" / f"{name}.exe",
            Path(sumo_home) / "tools" / name,
            Path(sumo_home) / "tools" / f"{name}.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    raise RuntimeError(
        f"Could not find {name}. Install SUMO and ensure its bin/tools "
        "directories are available on PATH or via SUMO_HOME."
    )


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> None:
    SIM.mkdir(exist_ok=True)

    netgenerate = find_tool("netgenerate")
    random_trips = find_tool("randomTrips.py")

    network = SIM / "network.net.xml"
    routes = SIM / "traffic.rou.xml"
    config = SIM / "green-corridor.sumocfg"

    run([
        netgenerate,
        "--grid",
        "--grid.number=3",
        "--grid.length=250",
        "--grid.attach-length=100",
        "--tls.guess",
        "--tls.guess.threshold=0",
        f"--output-file={network}",
    ])

    trips_command = (
        [sys.executable, random_trips]
        if random_trips.endswith(".py")
        else [random_trips]
    )
    run(trips_command + [
        "-n", str(network),
        "-r", str(routes),
        "-e", "600",
        "--period", "2.0",
        "--prefix", "car",
        "--min-distance", "200",
    ])

    config.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{network.name}"/>
        <route-files value="{routes.name}"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="600"/>
        <step-length value="0.2"/>
    </time>
    <processing>
        <time-to-teleport value="120"/>
    </processing>
    <report>
        <no-step-log value="true"/>
        <duration-log.disable value="true"/>
    </report>
</configuration>
""",
        encoding="utf-8",
    )

    print("\nSimulation files generated successfully:")
    print(f"  Network: {network}")
    print(f"  Routes:  {routes}")
    print(f"  Config:  {config}")
    print("\nNext: python run_simulation.py")


if __name__ == "__main__":
    main()
