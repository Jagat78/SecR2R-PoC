# SecR2R Podman Simulation Skeleton

This folder provides a minimal three-party SecR2R-like simulation:
- Robot A (`robot_a`)
- Robot B (`robot_b`)
- Authentication Server (`server`)
- Replay attacker script (`attacker/replay_attack.py`)

## 1) Start Podman

```powershell
podman machine start
```

If `podman-compose` is not globally available, use the workspace venv executable:

```powershell
..\.venv\Scripts\podman-compose.exe version
```

## 2) Run the stack

From this folder:

```powershell
podman-compose up --build -d
```

Fallback:

```powershell
..\.venv\Scripts\podman-compose.exe up --build -d
```

Health checks:

```powershell
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

## 3) Register robots

```powershell
curl -X POST http://localhost:8000/register -H "Content-Type: application/json" -d "{\"robot_id\":\"R_A\",\"attributes\":{\"joint\":\"A1\",\"sensor\":\"S1\"}}"
curl -X POST http://localhost:8000/register -H "Content-Type: application/json" -d "{\"robot_id\":\"R_B\",\"attributes\":{\"joint\":\"B1\",\"sensor\":\"S2\"}}"
```

## 4) Run one session from Robot A

```powershell
curl -X POST http://localhost:8001/session-run -H "Content-Type: application/json" -d "{\"target_robot\":\"R_B\",\"attributes\":{\"joint\":\"A1\",\"sensor\":\"S1\"}}"
```

The response includes `accepted` and a derived `session_key`.

## 5) Replay attack test

Run from host Python (or inside any container):

```powershell
python attacker/replay_attack.py --server http://localhost:8000 --delay 40
```

Expected behavior:
- First M1_a typically accepted
- Replayed stale M1_a rejected with timestamp freshness error (`408`)

## 6) Metrics output

CSV metrics are written to `logs/`:
- `logs/server_metrics.csv`
- `logs/robot_a_metrics.csv`
- `logs/robot_b_metrics.csv`
- `logs/paper_metrics_summary_YYYYMMDD_HHMMSS.csv` (per-run aggregate table)
- `logs/paper_metrics_summary_latest.csv` (latest aggregate table)

Each row captures event latency and bytes-in/out to support manuscript tables.

## 7) Stop stack

```powershell
podman-compose down
```

Fallback:

```powershell
..\.venv\Scripts\podman-compose.exe down
```

## One-click automation (recommended)

Run the full flow in one command (start stack, health checks, registration, baseline session, replay test, metrics summary):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1 -Rebuild
```

The script auto-detects available compose runners in this order:
1. global `podman-compose`
2. workspace `..\\.venv\\Scripts\\podman-compose.exe`
3. `podman compose` plugin provider

Useful options:

```powershell
# Skip replay test
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1 -SkipReplay

# Stop containers after run
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1 -StopWhenDone
```

## Notes

- This is a protocol-emulation scaffold for experimentation, not production crypto.
- Keep ProVerif for formal guarantees; use this setup for timing, bandwidth, and attack-flow validation.
