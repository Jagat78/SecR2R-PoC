import os
import uuid

import httpx
from fastapi import FastAPI, HTTPException

from common.crypto_utils import fake_puf, gen, h, now_ts, rep
from common.metrics import MetricLogger, MetricRecord, measure
from common.models import M1A, M2S, MB, M1S, SessionRunRequest, SessionRunResponse

app = FastAPI(title="SecR2R Robot A")

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
ROBOT_B_URL = os.getenv("ROBOT_B_URL", "http://localhost:8002")
ROBOT_ID = os.getenv("ROBOT_ID", "R_A")
LOG_DIR = os.getenv("LOG_DIR", "./logs")
ALLOWED_SKEW_SECONDS = int(os.getenv("ALLOWED_SKEW_SECONDS", "30"))
metrics = MetricLogger("robot_a", LOG_DIR)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "robot_a", "robot_id": ROBOT_ID}


@app.post("/session-run", response_model=SessionRunResponse)
def run_session(req: SessionRunRequest) -> SessionRunResponse:
    with measure() as elapsed:
        session_id = str(uuid.uuid4())

        # Step 0 local reconstruction placeholders (PUF + fuzzy extractor).
        fp = fake_puf(req.attributes)
        helper, _secret = gen(fp)
        theta_star = rep(fp, helper)

        c1 = h("c1", session_id, theta_star)
        c3 = h("c3", ROBOT_ID, req.target_robot, theta_star)
        c4 = h("c4", req.target_robot, c1)
        t_a = now_ts()
        c5 = h(session_id, ROBOT_ID, req.target_robot, c1, str(t_a))

        m1a = M1A(
            session_id=session_id,
            from_robot=ROBOT_ID,
            to_robot=req.target_robot,
            c1=c1,
            c3=c3,
            c4=c4,
            c5=c5,
            t_a=t_a,
        )

        with httpx.Client(timeout=10.0) as client:
            r1 = client.post(f"{SERVER_URL}/step1", json=m1a.model_dump())
            if r1.status_code != 200:
                raise HTTPException(status_code=r1.status_code, detail=f"step1 failed: {r1.text}")
            m1s = M1S(**r1.json())

            r2 = client.post(f"{ROBOT_B_URL}/step2", json=m1s.model_dump())
            if r2.status_code != 200:
                raise HTTPException(status_code=r2.status_code, detail=f"step2 failed: {r2.text}")
            mb = MB(**r2.json())

            r3 = client.post(f"{SERVER_URL}/step3", json=mb.model_dump())
            if r3.status_code != 200:
                raise HTTPException(status_code=r3.status_code, detail=f"step3 failed: {r3.text}")
            m2s = M2S(**r3.json())

        if abs(now_ts() - m2s.t2_s) > ALLOWED_SKEW_SECONDS:
            return SessionRunResponse(
                session_id=session_id,
                accepted=False,
                reason="stale timestamp in M2_s",
            )

        expected_y6 = h("y6", m2s.y4, m2s.y5, str(m2s.t2_s))
        if expected_y6 != m2s.y6:
            return SessionRunResponse(
                session_id=session_id,
                accepted=False,
                reason="M2_s integrity verification failed",
            )

        s_key = h("sk", session_id, m1a.c1, mb.w1, m2s.y4)

    metrics.log(
        MetricRecord(
            component="robot_a",
            event="run_session",
            elapsed_ms=elapsed(),
            bytes_in=len(req.model_dump_json()),
            bytes_out=160,
            ok=True,
        )
    )
    return SessionRunResponse(
        session_id=session_id,
        accepted=True,
        reason="ok",
        session_key=s_key,
    )
