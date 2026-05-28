import argparse
import time
import uuid

import httpx

from common.crypto_utils import h


def build_m1a(session_id: str, from_robot: str, to_robot: str, ts: int) -> dict:
    c1 = h("c1", session_id, "replay")
    return {
        "session_id": session_id,
        "from_robot": from_robot,
        "to_robot": to_robot,
        "c1": c1,
        "c3": h("c3", from_robot, to_robot),
        "c4": h("c4", to_robot, c1),
        "c5": h(session_id, from_robot, to_robot, c1, str(ts)),
        "t_a": ts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay M1_a attack simulator")
    parser.add_argument("--server", default="http://localhost:8000", help="Server base URL")
    parser.add_argument("--from-robot", default="R_A")
    parser.add_argument("--to-robot", default="R_B")
    parser.add_argument("--delay", type=int, default=40, help="Replay delay seconds")
    args = parser.parse_args()

    session_id = str(uuid.uuid4())
    ts = int(time.time())
    m1a = build_m1a(session_id, args.from_robot, args.to_robot, ts)

    with httpx.Client(timeout=10.0) as client:
        first = client.post(f"{args.server}/step1", json=m1a)
        print(f"[1] First send: status={first.status_code} body={first.text}")

        print(f"Waiting {args.delay}s before replay...")
        time.sleep(args.delay)

        second = client.post(f"{args.server}/step1", json=m1a)
        print(f"[2] Replay send: status={second.status_code} body={second.text}")


if __name__ == "__main__":
    main()
