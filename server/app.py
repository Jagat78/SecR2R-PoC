import json
import os

from fastapi import FastAPI, HTTPException

from common.crypto_utils import fresh_nonce, h, now_ts
from common.metrics import MetricLogger, MetricRecord, measure
from common.models import M1A, M1S, M2S, MB, RegisterRequest, RegisterResponse

app = FastAPI(title="SecR2R Server")

ALLOWED_SKEW_SECONDS = int(os.getenv("ALLOWED_SKEW_SECONDS", "30"))
LOG_DIR = os.getenv("LOG_DIR", "./logs")
metrics = MetricLogger("server", LOG_DIR)

# In-memory state for the simulation scaffold.
registry: dict[str, dict[str, str]] = {}
sessions: dict[str, dict[str, str]] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "server"}


@app.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest) -> RegisterResponse:
    """Registration Phase (Step 0)"""
    with measure() as elapsed:
        registry[req.robot_id] = {
            "bind": h(req.robot_id, json.dumps(req.attributes, sort_keys=True)),
            "status": "registered",
        }
    payload_out = len(req.model_dump_json())
    metrics.log(MetricRecord(
        component="server", event="register", elapsed_ms=elapsed(), bytes_in=payload_out, bytes_out=64, ok=True))
    return RegisterResponse(robot_id=req.robot_id, status="registered")


@app.post("/step1", response_model=M1S)
def step1(msg: M1A) -> M1S:
    raw_in = msg.model_dump_json()
    with measure() as elapsed:
        if msg.from_robot not in registry or msg.to_robot not in registry:
            raise HTTPException(status_code=403, detail="robot not registered")

        if abs(now_ts() - msg.t_a) > ALLOWED_SKEW_SECONDS:
            raise HTTPException(status_code=408, detail="stale timestamp in M1_a")

        expected_c5 = h(msg.session_id, msg.from_robot, msg.to_robot, msg.c1, str(msg.t_a))
        if expected_c5 != msg.c5:
            raise HTTPException(status_code=401, detail="invalid C5")

        n_s = fresh_nonce()
        t1_s = now_ts()
        y1 = h("y1", msg.session_id, n_s)
        y2 = h("y2", msg.c1, n_s)
        y3 = h("y3", y1, y2, str(t1_s))

        sessions[msg.session_id] = {
            "from_robot": msg.from_robot,
            "to_robot": msg.to_robot,
            "c1": msg.c1,
            "n_s": n_s,
            "t1_s": str(t1_s),
        }

        out = M1S(
            session_id=msg.session_id,
            y1=y1,
            y2=y2,
            y3=y3,
            t1_s=t1_s,
            from_robot=msg.from_robot,
            to_robot=msg.to_robot,
        )

    metrics.log(MetricRecord(component="server", event="step1", elapsed_ms=elapsed(), bytes_in=len(raw_in), bytes_out=len(out.model_dump_json()), ok=True))
    return out


@app.post("/step3", response_model=M2S)
def step3(msg: MB) -> M2S:
    raw_in = msg.model_dump_json()
    with measure() as elapsed:
        if msg.session_id not in sessions:
            raise HTTPException(status_code=404, detail="unknown session")

        state = sessions[msg.session_id]

        if abs(now_ts() - msg.t_b) > ALLOWED_SKEW_SECONDS:
            raise HTTPException(status_code=408, detail="stale timestamp in M_b")

        expected_w4 = h(msg.session_id, msg.from_robot, msg.w1, str(msg.t_b))
        if expected_w4 != msg.w4:
            raise HTTPException(status_code=401, detail="invalid W4")

        u_s = fresh_nonce()
        t2_s = now_ts()
        y4 = h("y4", msg.session_id, u_s)
        y5 = h("y5", msg.w1, u_s)
        y6 = h("y6", y4, y5, str(t2_s))

        sessions[msg.session_id]["u_s"] = u_s
        sessions[msg.session_id]["w1"] = msg.w1

        out = M2S(session_id=msg.session_id, y4=y4, y5=y5, y6=y6, t2_s=t2_s)

    metrics.log(
        MetricRecord(
            component="server",
            event="step3",
            elapsed_ms=elapsed(),
            bytes_in=len(raw_in),
            bytes_out=len(out.model_dump_json()),
            ok=True,
        )
    )
    return out
