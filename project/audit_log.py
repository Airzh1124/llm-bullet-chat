from __future__ import annotations

import csv
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(
        self,
        enabled: bool = True,
        directory: Path | str = "logs",
        text_limit: int = 4000,
    ) -> None:
        self.enabled = enabled
        self.directory = Path(directory)
        self.text_limit = max(200, text_limit)
        self._lock = threading.Lock()
        self._step_index = 0
        self.path: Path | None = None

        if not self.enabled:
            return

        self.directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.directory / f"audit_{timestamp}.csv"
        with self.path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames())
            writer.writeheader()

    def record(
        self,
        step: str,
        *,
        collected_text: str = "",
        uploaded_data: Any = "",
        result: Any = "",
        detail: str = "",
        changed: bool | None = None,
        diff_score: float | None = None,
    ) -> None:
        if not self.enabled or self.path is None:
            return

        with self._lock:
            self._step_index += 1
            row = {
                "step_index": self._step_index,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "step": step,
                "changed": "" if changed is None else str(changed).lower(),
                "diff_score": "" if diff_score is None else f"{diff_score:.3f}",
                "collected_text": self._serialize(collected_text),
                "uploaded_data": self._serialize(uploaded_data),
                "result": self._serialize(result),
                "detail": detail,
            }
            with self.path.open("a", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._fieldnames())
                writer.writerow(row)

    def _serialize(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False, default=str)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > self.text_limit:
            return text[: self.text_limit] + "...[truncated]"
        return text

    @staticmethod
    def _fieldnames() -> list[str]:
        return [
            "step_index",
            "timestamp",
            "step",
            "changed",
            "diff_score",
            "collected_text",
            "uploaded_data",
            "result",
            "detail",
        ]


class NullAuditLog(AuditLog):
    def __init__(self) -> None:
        self.enabled = False
        self.path = None

    def record(self, *args: Any, **kwargs: Any) -> None:
        return
