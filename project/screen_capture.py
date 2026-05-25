from __future__ import annotations

from dataclasses import dataclass

import cv2
import mss
import numpy as np


@dataclass
class CaptureResult:
    image_bgr: np.ndarray
    changed: bool
    diff_score: float


class ScreenCapture:
    """Screen capture built around mss' public API.

    Reference idea: python-mss examples use `mss().grab(monitor)` and convert the
    BGRA buffer with numpy. This module adds small-frame diffing for MVP throttling.
    """

    def __init__(
        self,
        monitor_index: int = 1,
        region: dict[str, int] | None = None,
        change_threshold: float = 4.0,
    ) -> None:
        self.monitor_index = monitor_index
        self.region = region
        self.change_threshold = change_threshold
        self._last_small_gray: np.ndarray | None = None

    def capture(self) -> CaptureResult:
        with mss.mss() as sct:
            monitor = self._get_monitor(sct)
            raw = sct.grab(monitor)

        frame = np.asarray(raw)
        image_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        small_gray = self._small_gray(image_bgr)

        if self._last_small_gray is None:
            self._last_small_gray = small_gray
            return CaptureResult(image_bgr=image_bgr, changed=True, diff_score=999.0)

        diff_score = float(
            np.mean(cv2.absdiff(self._last_small_gray, small_gray))
        )
        changed = diff_score >= self.change_threshold
        if changed:
            self._last_small_gray = small_gray

        return CaptureResult(image_bgr=image_bgr, changed=changed, diff_score=diff_score)

    def _get_monitor(self, sct: mss.mss) -> dict[str, int]:
        if self.region:
            return self.region

        monitors = sct.monitors
        if self.monitor_index < 0 or self.monitor_index >= len(monitors):
            return monitors[1] if len(monitors) > 1 else monitors[0]
        return monitors[self.monitor_index]

    @staticmethod
    def _small_gray(image_bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (96, 54), interpolation=cv2.INTER_AREA)
