from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect, QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QWidget


@dataclass
class DanmakuItem:
    label: QLabel
    speed: int
    track_y: int


class DanmakuOverlay(QWidget):
    """Transparent top-most overlay using Qt window flags.

    Reference ideas: common PyQt transparent overlay examples combine
    FramelessWindowHint, WindowStaysOnTopHint, WA_TranslucentBackground and
    WindowTransparentForInput for click-through behavior. Animation is handled
    locally with a timer so labels can be removed once off-screen.
    """

    def __init__(
        self,
        font_size: int = 28,
        font_family: str = "Microsoft YaHei UI",
        color: str = "#FFFFFF",
        speed_min: int = 90,
        speed_max: int = 170,
        spawn_interval_min_ms: int = 650,
        spawn_interval_max_ms: int = 1600,
        area_top_ratio: float = 0.08,
        area_bottom_ratio: float = 0.55,
        track_gap_px: int = 360,
        max_danmaku: int = 80,
        click_through: bool = True,
        opacity: float = 0.92,
    ) -> None:
        super().__init__()
        self.font_size = font_size
        self.font_family = font_family
        self.color = color
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.spawn_interval_min_ms = spawn_interval_min_ms
        self.spawn_interval_max_ms = spawn_interval_max_ms
        self.area_top_ratio = area_top_ratio
        self.area_bottom_ratio = area_bottom_ratio
        self.track_gap_px = track_gap_px
        self.max_danmaku = max_danmaku
        self.items: list[DanmakuItem] = []
        self.pending: deque[str] = deque()
        self.recent_texts: deque[str] = deque(maxlen=max_danmaku * 2)
        self._tracks: list[int] = []

        self._configure_window(click_through, opacity)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.spawn_timer = QTimer(self)
        self.spawn_timer.timeout.connect(self._spawn_next_pending)
        self._schedule_next_spawn()

    def _configure_window(self, click_through: bool, opacity: float) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(max(0.1, min(opacity, 1.0)))

        screen = QGuiApplication.primaryScreen()
        geometry = screen.geometry() if screen else QRect(0, 0, 1280, 720)
        self.setGeometry(geometry)
        self._tracks = self._build_tracks(geometry.height())

    def _build_tracks(self, height: int) -> list[int]:
        top_margin = max(0, min(height - 1, int(height * self.area_top_ratio)))
        bottom_line = max(top_margin + 1, min(height, int(height * self.area_bottom_ratio)))
        step = max(self.font_size + 12, 36)
        return list(range(top_margin, bottom_line, step)) or [top_margin]

    @pyqtSlot(str)
    def add_danmaku(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text in self.recent_texts or text in self.pending:
            return
        self.pending.append(text)

    @pyqtSlot(list)
    def add_danmaku_batch(self, texts: list[str]) -> None:
        for text in texts:
            self.add_danmaku(text)

    def _spawn_next_pending(self) -> None:
        if not self.pending:
            self._schedule_next_spawn()
            return

        track_y = self._choose_available_track()
        if track_y is None:
            self.spawn_timer.start(250)
            return

        text = self.pending.popleft()
        while len(self.items) >= self.max_danmaku:
            self._remove_item(self.items[0])

        label = QLabel(text, self)
        label.setFont(QFont(self.font_family, self.font_size, QFont.Weight.Bold))
        label.setAutoFillBackground(False)
        label.setPalette(self._text_palette())
        label.setStyleSheet(
            f"QLabel {{ color: {self.color}; background: transparent; "
            "text-shadow: 2px 2px 2px rgba(0, 0, 0, 190); }"
        )
        label.adjustSize()

        x = self.width() + random.randint(0, 160)
        label.move(QPoint(x, track_y))
        label.show()

        speed = random.randint(self.speed_min, self.speed_max)
        self.items.append(DanmakuItem(label=label, speed=speed, track_y=track_y))
        self.recent_texts.append(text)
        self._schedule_next_spawn()

    def _choose_available_track(self) -> int | None:
        if not self._tracks:
            return random.randint(20, max(20, self.height() - 60))

        tracks = self._tracks[:]
        random.shuffle(tracks)
        for track_y in tracks:
            if self._track_is_available(track_y):
                return track_y
        return None

    def _track_is_available(self, track_y: int) -> bool:
        same_track = [item for item in self.items if item.track_y == track_y]
        if not same_track:
            return True

        rightmost_edge = max(item.label.x() + item.label.width() for item in same_track)
        return rightmost_edge < self.width() - self.track_gap_px

    def _schedule_next_spawn(self) -> None:
        low = max(100, min(self.spawn_interval_min_ms, self.spawn_interval_max_ms))
        high = max(low, self.spawn_interval_max_ms)
        self.spawn_timer.start(random.randint(low, high))

    def _tick(self) -> None:
        dt = self.timer.interval() / 1000.0
        for item in list(self.items):
            label = item.label
            label.move(int(label.x() - item.speed * dt), label.y())
            if label.x() + label.width() < 0:
                self._remove_item(item)

    def _remove_item(self, item: DanmakuItem) -> None:
        if item in self.items:
            self.items.remove(item)
        item.label.hide()
        item.label.deleteLater()

    @staticmethod
    def _text_palette() -> QPalette:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        return palette


def create_app() -> QApplication:
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])
