# Green Corridor

Green Corridor is a local emergency mobility command centre backed by a SUMO traffic simulation. It provides a React dashboard, a FastAPI service, network routing, a TraCI-owned simulation worker, SQLite trip/event history, and WebSocket state updates. It is a simulation and does not connect to real traffic infrastructure.

## Requirements

- Python 3.9 or newer
- Node.js 18 or newer
- SUMO 1.28 or compatible, including `sumo` and Python tools (`traci`, `sumolib`)

The repository includes its generated 3×3 network and civilian routes. If you need to regenerate them, see `scripts/setup_simulation.py` and make sure `netgenerate` and `randomTrips.py` are available.

## Start locally

In one terminal, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

If your SUMO installation does not expose its Python modules to this environment, set `SUMO_HOME` to the SUMO installation's `share/sumo` directory. The backend also adds `$SUMO_HOME/tools` to Python's import path.

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. API documentation is at <http://127.0.0.1:8000/docs>. Use **Start simulation** in the app before dispatching an emergency.

## Product sections

- **Command centre:** Live SUMO network, vehicles, signals, active trip, and event feed.
- **Emergency dispatch:** Select origin/destination road edges, choose severity, and create a persisted trip.
- **Route intelligence:** Inspect the actual routed edge sequence and request a traffic-weighted recalculation.
- **Signal management:** View the state reported for each SUMO traffic light.
- **Analytics:** Review completed trip durations and persisted event counts. Unavailable comparisons are labelled as unavailable.

## Backend behavior

- `SimulationManager` owns TraCI in one worker thread. API requests hand commands to that worker; WebSocket clients receive snapshots.
- NetworkX finds a route on the directed SUMO road graph. When SUMO is running, edge weights use measured speed and vehicle count.
- `SignalController` reads the ambulance's next controlled link from TraCI, clears active greens to yellow, holds all-red, gives the reported link priority, detects passage by outgoing edge, and resumes the normal program. The included controller currently handles one active junction priority request at a time.
- SQLite is created at `data/green_corridor.sqlite3` and is ignored by Git.

## API

`GET /api/health`, `GET /api/network`, `GET /api/simulation/state`, `POST /api/simulation/start`, `POST /api/simulation/stop`, `GET /api/edges`, `POST /api/routes/preview`, `POST /api/emergencies`, `GET /api/emergencies`, `GET /api/emergencies/{id}`, `POST /api/emergencies/{id}/reroute`, `GET /api/intersections`, `GET /api/analytics`, `GET /api/events`, and `WS /ws/live`.

## Compatibility launcher

The standalone SUMO controller is available with:

```bash
python run_simulation.py --nogui
```

The web backend is the normal way to operate the project.
