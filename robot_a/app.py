# Test print to check container stdout capture
import sys

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
    with measure() as session_elapsed:
        session_id = str(uuid.uuid4())
        # Step 1: R_a -> AS
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
        logger.info("run_session: constructed m1a")
        metrics.log(MetricRecord(component="robot_a", event="step1", elapsed_ms=session_elapsed(), bytes_in=0, bytes_out=len(str(m1a)), ok=True))

        with httpx.Client(timeout=10.0) as client:
            logger.info("run_session: httpx.Client entered")
            logger.debug("Step 1: Sending to server /step1")
            r1 = client.post(f"{SERVER_URL}/step1", json=m1a.model_dump())
            logger.debug(f"Step 1: Response status {r1.status_code}")
            if r1.status_code != 200:
                logger.error("run_session: step1 failed, returning early")
                logger.debug(f"Step 1: Failed with {r1.text}")
                raise HTTPException(status_code=r1.status_code, detail=f"step1 failed: {r1.text}")
            m1s = M1S(**r1.json())
            logger.debug("Step 1: Success, logging step1_ack")
            metrics.log(MetricRecord(component="robot_a", event="step1_ack", elapsed_ms=session_elapsed(), bytes_in=len(str(m1s)), bytes_out=0, ok=True))

            logger.debug("Step 2: Sending to robot_b /step2")
            r2 = client.post(f"{ROBOT_B_URL}/step2", json=m1s.model_dump())
            logger.debug(f"Step 2: Response status {r2.status_code}")
            if r2.status_code != 200:
                logger.error("run_session: step2 failed, returning early")
                logger.debug(f"Step 2: Failed with {r2.text}")
                raise HTTPException(status_code=r2.status_code, detail=f"step2 failed: {r2.text}")
            mb = MB(**r2.json())
            logger.debug("Step 2: Success, logging step2_ack")
            metrics.log(MetricRecord(component="robot_a", event="step2_ack", elapsed_ms=session_elapsed(), bytes_in=len(str(mb)), bytes_out=0, ok=True))

            logger.debug("Step 3: Sending to server /step3")
            r3 = client.post(f"{SERVER_URL}/step3", json=mb.model_dump())
            logger.debug(f"Step 3: Response status {r3.status_code}")
            if r3.status_code != 200:
                logger.error("run_session: step3 failed, returning early")
                logger.debug(f"Step 3: Failed with {r3.text}")
                raise HTTPException(status_code=r3.status_code, detail=f"step3 failed: {r3.text}")
            try:
                m2s_json = r3.json()
                logger.info(f"Step 3: Received JSON from server: {m2s_json}")
                m2s = M2S(**m2s_json)
            except Exception as e:
                logger.error(f"run_session: Exception while parsing M2S: {e}")
                logger.error(f"run_session: Raw response text: {r3.text}")
                logger.error(f"Step 3: Exception while parsing M2S: {e}")
                logger.error(f"Step 3: Raw response text: {r3.text}")
                raise
            logger.debug("Step 3: Success, logging step3_ack")
            metrics.log(MetricRecord(component="robot_a", event="step3_ack", elapsed_ms=session_elapsed(), bytes_in=len(str(m2s)), bytes_out=0, ok=True))


        logger.debug("Before Step 4: About to validate server reply")
        logger.info("run_session: before step 4 validation")
        # Step 4: Validate server reply (timing only validation)
        with measure() as step4_elapsed:
            if abs(now_ts() - m2s.t2_s) > ALLOWED_SKEW_SECONDS:
                logger.warning("run_session: step4_fail, timestamp skew too large")
                logger.debug("Step 4: Timestamp skew too large, logging step4_fail")
                metrics.log(MetricRecord(component="robot_a", event="step4_fail", elapsed_ms=step4_elapsed(), bytes_in=0, bytes_out=0, ok=False))
                logger.info("run_session: returning after step4_fail")
                return SessionRunResponse(
                    session_id=session_id,
                    accepted=False,
                    reason="stale timestamp in M2_s",
                )
            else:
                logger.info("run_session: step4 validation passed, logging step4")
                logger.debug("Step 4: Logging step4 metric (timestamp OK)")
                metrics.log(MetricRecord(component="robot_a", event="step4", elapsed_ms=step4_elapsed(), bytes_in=0, bytes_out=0, ok=True))
                logger.debug("Step 4: step4 metric logged")

        expected_y6 = h("y6", m2s.y4, m2s.y5, str(m2s.t2_s))
        if expected_y6 != m2s.y6:
            logger.warning("run_session: step5_fail, Y6 mismatch")
            metrics.log(MetricRecord(component="robot_a", event="step5_fail", elapsed_ms=session_elapsed(), bytes_in=0, bytes_out=0, ok=False))
            logger.info("run_session: returning after step5_fail")
            return SessionRunResponse(
                session_id=session_id,
                accepted=False,
                reason="M2_s integrity verification failed",
            )

        s_key = h("sk", session_id, m1a.c1, mb.w1, m2s.y4)
        metrics.log(MetricRecord(component="robot_a", event="step5", elapsed_ms=session_elapsed(), bytes_in=0, bytes_out=0, ok=True))
        logger.info("run_session: completed successfully, returning session key")

    return SessionRunResponse(
        session_id=session_id,
        accepted=True,
        reason="ok",
        session_key=s_key,
    )
