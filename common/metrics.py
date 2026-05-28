import csv
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class MetricRecord:
    component: str
    event: str
    elapsed_ms: float
    bytes_in: int
    bytes_out: int
    ok: bool


class MetricLogger:
    def __init__(self, component: str, log_dir: str) -> None:
        self.component = component
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, f"{component}_metrics.csv")
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["component", "event", "elapsed_ms", "bytes_in", "bytes_out", "ok"])

    def log(self, rec: MetricRecord) -> None:
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                rec.component,
                rec.event,
                f"{rec.elapsed_ms:.3f}",
                rec.bytes_in,
                rec.bytes_out,
                int(rec.ok),
            ])


@contextmanager
def measure():
    start = time.perf_counter()
    try:
        yield lambda: (time.perf_counter() - start) * 1000.0
    finally:
        pass
