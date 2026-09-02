from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNS_DIR = Path(__file__).resolve().parents[1] / "data" / "runs"


class RunStore:
    def __init__(self, run_id: str) -> None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RUNS_DIR / f"{run_id}.jsonl"
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

