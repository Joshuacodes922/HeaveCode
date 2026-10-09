"""Small JSONL event logger with no external observability dependency."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventLogger:
    def __init__(self, log_path: str | Path) -> None:
        self.logger = logging.getLogger(f"coding_agent.{Path(log_path).resolve()}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def log(self, event: str, **fields: Any) -> None:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self.logger.info(json.dumps(payload, default=str))

    def close(self) -> None:
        """Close file handles explicitly (useful for tests and short-lived workers)."""
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
