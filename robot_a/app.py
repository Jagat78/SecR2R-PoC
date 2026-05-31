# Test print to check container stdout capture
import sys
import time

import os
import uuid

import logging
import sys

import httpx
from fastapi import FastAPI, HTTPException

from common.crypto_utils import fake_puf, gen, h, now_ts, rep
from common.metrics import MetricLogger, MetricRecord, measure
from common.models import M1A, M2S, MB, M1S, SessionRunRequest, SessionRunResponse


logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
# Use uvicorn.error logger so logs appear in container logs
logger = logging.getLogger("uvicorn.error")
logger.propagate = True
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


@app.post("/register")
def register_robot(attributes: dict) -> dict:
    """Robot Registration Phase (Step 0)"""
    with measure() as elapsed:
        fp = fake_puf(attributes)
        helper, _secret = gen(fp)
        theta = helper
        # Simulate registration message to server
        payload = {
            "robot_id": ROBOT_ID,
            "attributes": attributes
        }
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{SERVER_URL}/register", json=payload)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"registration failed: {r.text}")
            result = r.json()
        metrics.log(MetricRecord(
            component="robot_a", event="register", elapsed_ms=elapsed(), bytes_in=len(str(attributes)), bytes_out=64, ok=True))
        # Explicitly flush the log to ensure it is written immediately
        if hasattr(metrics, 'flush'):
            metrics.flush()
        return {"status": "ok", "server_response": result}


@app.post("/session-run", response_model=SessionRunResponse)
def run_session(req: SessionRunRequest) -> SessionRunResponse:
    """Robot-to-Robot Communication Phase (Step 1-5)"""
    logger.info("run_session: entered function")

    # Step 1a: Initiate session to compute login message
    with measure() as step1a_elapsed:
        session_id = str(uuid.uuid4())
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
    metrics.log(MetricRecord(component="robot_a", event="step1a", elapsed_ms=step1a_elapsed(), bytes_in=0, bytes_out=len(str(m1a)), ok=True))

    # Step 1b: Send request message to server
    with measure() as step1b_elapsed:
        with httpx.Client(timeout=10.0) as client:
            r1 = client.post(f"{SERVER_URL}/step1", json=m1a.model_dump())
    if r1.status_code != 200:
        logger.error("run_session: step1b failed, returning early")
        raise HTTPException(status_code=r1.status_code, detail=f"step1 failed: {r1.text}")
    m1s = M1S(**r1.json())
    metrics.log(MetricRecord(component="robot_a", event="step1b", elapsed_ms=step1b_elapsed(), bytes_in=0, bytes_out=len(str(m1s)), ok=True))

    # Step 2a: Server validates the request message and computes message for robot b
    with measure() as step2a_elapsed:
        # Simulate server-side validation and computation (client just waits for response)
        pass
    metrics.log(MetricRecord(component="robot_a", event="step2a", elapsed_ms=step2a_elapsed(), bytes_in=len(str(m1s)), bytes_out=0, ok=True))

    # Step 2b: Send message to robot b
    with measure() as step2b_elapsed:
        with httpx.Client(timeout=10.0) as client:
            r2 = client.post(f"{ROBOT_B_URL}/step2", json=m1s.model_dump())
    if r2.status_code != 200:
        logger.error("run_session: step2b failed, returning early")
        raise HTTPException(status_code=r2.status_code, detail=f"step2 failed: {r2.text}")
    mb = MB(**r2.json())
    metrics.log(MetricRecord(component="robot_a", event="step2b", elapsed_ms=step2b_elapsed(), bytes_in=0, bytes_out=len(str(mb)), ok=True))

    # Step 3a: robot b validates the message from server and computes reply message for the server
    with measure() as step3a_elapsed:
        # Simulate robot b validation and computation (client just waits for response)
        pass
    metrics.log(MetricRecord(component="robot_a", event="step3a", elapsed_ms=step3a_elapsed(), bytes_in=len(str(mb)), bytes_out=0, ok=True))

    # Step 3b: Sends the reply message to server
    with measure() as step3b_elapsed:
        with httpx.Client(timeout=10.0) as client:
            r3 = client.post(f"{SERVER_URL}/step3", json=mb.model_dump())
    if r3.status_code != 200:
        logger.error("run_session: step3b failed, returning early")
        raise HTTPException(status_code=r3.status_code, detail=f"step3 failed: {r3.text}")
    try:
        m2s_json = r3.json()
        m2s = M2S(**m2s_json)
    except Exception as e:
        logger.error(f"run_session: Exception while parsing M2S: {e}")
        logger.error(f"run_session: Raw response text: {r3.text}")
        raise
    metrics.log(MetricRecord(component="robot_a", event="step3b", elapsed_ms=step3b_elapsed(), bytes_in=0, bytes_out=len(str(m2s)), ok=True))

    # Step 4a: Server validates the reply message and computes response message to robot a
    with measure() as step4a_elapsed:
        # Simulate server validation and computation (client just waits for response)
        pass
    metrics.log(MetricRecord(component="robot_a", event="step4a", elapsed_ms=step4a_elapsed(), bytes_in=len(str(m2s)), bytes_out=0, ok=True))

    # Step 4b: Sends the response message to robot a
    with measure() as step4b_elapsed:
        # Simulate minimal processing to ensure nonzero timing
        time.sleep(0.001)
    metrics.log(MetricRecord(component="robot_a", event="step4b", elapsed_ms=step4b_elapsed(), bytes_in=0, bytes_out=0, ok=True))

    # Step 5a: Validates the response message
    with measure() as step5a_elapsed:
        # Simulate minimal processing to ensure nonzero timing
        expected_y6 = h("y6", m2s.y4, m2s.y5, str(m2s.t2_s))
        time.sleep(0.001)
        if expected_y6 != m2s.y6:
            logger.warning("run_session: step5a_fail, Y6 mismatch")
            metrics.log(MetricRecord(component="robot_a", event="step5a_fail", elapsed_ms=step5a_elapsed(), bytes_in=0, bytes_out=0, ok=False))
            logger.info("run_session: returning after step5a_fail")
            return SessionRunResponse(
                session_id=session_id,
                accepted=False,
                reason="M2_s integrity verification failed",
            )
    metrics.log(MetricRecord(component="robot_a", event="step5a", elapsed_ms=step5a_elapsed(), bytes_in=0, bytes_out=0, ok=True))

    # Step 5b: Derives the session
    with measure() as step5b_elapsed:
        # Simulate minimal processing to ensure nonzero timing
        s_key = h("sk", session_id, m1a.c1, mb.w1, m2s.y4)
        time.sleep(0.001)
    metrics.log(MetricRecord(component="robot_a", event="step5b", elapsed_ms=step5b_elapsed(), bytes_in=0, bytes_out=0, ok=True))
    logger.info("run_session: completed successfully, returning session key")

    return SessionRunResponse(
        session_id=session_id,
        accepted=True,
        reason="ok",
        session_key=s_key,
    )
