import os

from fastapi import FastAPI, HTTPException

from common.crypto_utils import fresh_nonce, h, now_ts
from common.metrics import MetricLogger, MetricRecord, measure
from common.models import M1S, MB

app = FastAPI(title="SecR2R Robot B")

LOG_DIR = os.getenv("LOG_DIR", "./logs")
ROBOT_ID = os.getenv("ROBOT_ID", "R_B")
ALLOWED_SKEW_SECONDS = int(os.getenv("ALLOWED_SKEW_SECONDS", "30"))
metrics = MetricLogger("robot_b", LOG_DIR)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "robot_b", "robot_id": ROBOT_ID}


@app.post("/register")
def register_robot(attributes: dict) -> dict:
    """Robot Registration Phase (Step 0)"""
    with measure() as elapsed:
        # Simulate registration message to server
        payload = {
            "robot_id": ROBOT_ID,
            "attributes": attributes
        }
        import httpx
        with httpx.Client(timeout=10.0) as client:
            r = client.post("http://localhost:8000/register", json=payload)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"registration failed: {r.text}")
            result = r.json()
        metrics.log(MetricRecord(
            component="robot_b", event="register", elapsed_ms=elapsed(), bytes_in=len(str(attributes)), bytes_out=64, ok=True))
        return {"status": "ok", "server_response": result}


@app.post("/step2", response_model=MB)
def step2(msg: M1S) -> MB:
    raw_in = msg.model_dump_json()
    with measure() as elapsed:
        if msg.to_robot != ROBOT_ID:
            raise HTTPException(status_code=403, detail="wrong target robot")

        if abs(now_ts() - msg.t1_s) > ALLOWED_SKEW_SECONDS:
            raise HTTPException(status_code=408, detail="stale timestamp in M1_s")

        expected_y3 = h("y3", msg.y1, msg.y2, str(msg.t1_s))
        if expected_y3 != msg.y3:
            raise HTTPException(status_code=401, detail="invalid Y3")

        v_b = fresh_nonce()
        w1 = h("w1", msg.session_id, v_b)
        w3 = h("w3", msg.from_robot, ROBOT_ID, v_b)
        t_b = now_ts()
        w4 = h(msg.session_id, ROBOT_ID, w1, str(t_b))

        out = MB(
            session_id=msg.session_id,
            from_robot=ROBOT_ID,
            to_robot=msg.from_robot,
            w1=w1,
            w3=w3,
            w4=w4,
            t_b=t_b,
        )

    metrics.log(MetricRecord(component="robot_b", event="step2", elapsed_ms=elapsed(), bytes_in=len(raw_in), bytes_out=len(out.model_dump_json()), ok=True))
    return out
