# Green Corridor — Phase 1 Starter

A first runnable SUMO + Python simulation scaffold for the Green Corridor project.

**Phase 1 goal:** create a small signalised city network, populate it with civilian traffic, introduce one ambulance, and observe vehicle movement through SUMO.

This is a simulation only. It does not connect to or control real traffic signals.

## 1. Requirements

- SUMO (including `sumo`, `netgenerate`, `netconvert`, and `randomTrips.py`)
- Python 3.10+
- Python packages: `traci`, `sumolib`

### Install SUMO

- **macOS (Homebrew):** `brew install sumo`
- **Ubuntu/Debian:** `sudo apt install sumo sumo-tools`
- **Windows:** install SUMO from https://sumo.dlr.de/docs/Installing/index.html and add its `bin` and `tools` directories to your PATH / `SUMO_HOME`.

Check that these commands work:

```bash
sumo --version
netgenerate --help
```

If Python cannot import `traci` or `sumolib`, set `SUMO_HOME` to your SUMO installation directory and add `$SUMO_HOME/tools` to `PYTHONPATH`.

## 2. Create a Python environment

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 3. Generate the network and traffic

```bash
python scripts/setup_simulation.py
```

This creates:
- `simulation/network.net.xml` — a small 3 × 3 grid network with guessed traffic lights
- `simulation/traffic.rou.xml` — generated civilian vehicle routes
- `simulation/green-corridor.sumocfg` — SUMO configuration

## 4. Run the simulation

```bash
python run_simulation.py
```

Use the GUI by default. To run without the GUI:

```bash
python run_simulation.py --nogui
```

The script adds one ambulance after the simulation starts and asks SUMO to find a route across the network. Civilian traffic is generated from random trips.

## 5. What to verify

- The SUMO GUI opens.
- Civilian vehicles enter and travel through the network.
- A blue ambulance appears and follows a valid route.
- The simulation completes without Python exceptions.

At this stage, traffic lights use their normal SUMO signal programs. **Emergency signal preemption is not implemented yet.** That is Phase 3, after the network and TraCI connection are reliable.

## Project structure

```text
green-corridor/
├── README.md
├── requirements.txt
├── run_simulation.py
├── scripts/
│   └── setup_simulation.py
├── simulation/
│   └── (generated SUMO files)
└── data/
```

## Troubleshooting

### `SUMO_HOME is not set`
Set it to your SUMO installation directory. On macOS Homebrew, it is commonly `/opt/homebrew/opt/sumo/share/sumo` on Apple Silicon or `/usr/local/opt/sumo/share/sumo` on Intel. Verify the actual path on your machine.

### `netgenerate` or `randomTrips.py` not found
Ensure the SUMO `bin` directory and SUMO `tools` directory are installed and available. `randomTrips.py` is normally inside `$SUMO_HOME/tools`.

### `No route found for ambulance`
Regenerate the network and routes, then try again. The starter selects a connected pair of edges from the generated network and uses SUMO's routing engine.

### GUI does not open
Run with `--nogui`. This checks the simulation and TraCI integration without requiring a graphical display.

## Next milestone

Once this runs on your machine, the next build step is a deterministic ambulance route and a Python intersection-controller state machine. We will then add safe emergency preemption (clearance phases, passage confirmation, recovery, and communication-loss fallback).
