from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import QApplication, QLabel, QWidget


@dataclass
class DanmakuItem:
    label: QLabel
    speed: int
    track_y: int


@dataclass
class PanelItem:
    label: QLabel


class OutlinedLabel(QLabel):
    def __init__(
        self,
        text: str,
        parent: QWidget,
        *,
        text_color: str,
        outline_color: str,
        outline_width: int,
        background_alpha: int,
        padding_x: int = 8,
        padding_y: int = 4,
    ) -> None:
        super().__init__(text, parent)
        self.text_color = QColor(text_color)
        self.outline_color = QColor(outline_color)
        self.outline_width = max(0, outline_width)
        self.background_alpha = max(0, min(background_alpha, 255))
        self.padding_x = padding_x
        self.padding_y = padding_y
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        text_rect = metrics.boundingRect(self.text())
        pad = self.outline_width * 2
        return QSize(
            text_rect.width() + self.padding_x * 2 + pad,
            text_rect.height() + self.padding_y * 2 + pad,
        )

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if self.background_alpha > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, self.background_alpha))
            painter.drawRoundedRect(QRectF(self.rect()), 6, 6)

        metrics = QFontMetrics(self.font())
        baseline = self.padding_y + self.outline_width + metrics.ascent()
        path = QPainterPath()
        path.addText(self.padding_x + self.outline_width, baseline, self.font(), self.text())

        if self.outline_width > 0:
            pen = QPen(self.outline_color)
            pen.setWidth(self.outline_width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)

        painter.fillPath(path, self.text_color)
        painter.end()


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
        outline_color: str = "#000000",
        outline_width: int = 4,
        text_background_alpha: int = 0,
        mode: str = "floating",
        speed_min: int = 90,
        speed_max: int = 170,
        spawn_interval_min_ms: int = 650,
        spawn_interval_max_ms: int = 1600,
        area_top_ratio: float = 0.08,
        area_bottom_ratio: float = 0.55,
        track_gap_px: int = 360,
        panel_left_ratio: float = 0.70,
        panel_top_ratio: float = 0.12,
        panel_width_ratio: float = 0.28,
        panel_height_ratio: float = 0.55,
        panel_background_alpha: int = 70,
        panel_scroll_speed: int = 36,
        panel_line_gap: int = 8,
        panel_max_items: int = 40,
        max_danmaku: int = 80,
        click_through: bool = True,
        opacity: float = 0.92,
        keep_top_interval_ms: int = 2000,
    ) -> None:
        super().__init__()
        self.font_size = font_size
        self.font_family = font_family
        self.color = color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.text_background_alpha = text_background_alpha
        self.mode = mode
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.spawn_interval_min_ms = spawn_interval_min_ms
        self.spawn_interval_max_ms = spawn_interval_max_ms
        self.area_top_ratio = area_top_ratio
        self.area_bottom_ratio = area_bottom_ratio
        self.track_gap_px = track_gap_px
        self.panel_left_ratio = panel_left_ratio
        self.panel_top_ratio = panel_top_ratio
        self.panel_width_ratio = panel_width_ratio
        self.panel_height_ratio = panel_height_ratio
        self.panel_background_alpha = panel_background_alpha
        self.panel_scroll_speed = panel_scroll_speed
        self.panel_line_gap = panel_line_gap
        self.panel_max_items = panel_max_items
        self.max_danmaku = max_danmaku
        self.keep_top_interval_ms = keep_top_interval_ms
        self.items: list[DanmakuItem] = []
        self.panel_items: list[PanelItem] = []
        self.pending: deque[str] = deque()
        self.recent_texts: deque[str] = deque(maxlen=max_danmaku * 2)
        self._tracks: list[int] = []
        self._panel_rect = QRect(0, 0, 0, 0)
        self._panel_next_y = 0
        self.panel_widget = QWidget(self)

        self._configure_window(click_through, opacity)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.spawn_timer = QTimer(self)
        self.spawn_timer.timeout.connect(self._spawn_next_pending)
        self._schedule_next_spawn()

        self.keep_top_timer = QTimer(self)
        self.keep_top_timer.timeout.connect(self._keep_on_top)
        if self.keep_top_interval_ms > 0:
            self.keep_top_timer.start(self.keep_top_interval_ms)

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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, click_through)
        self.setWindowOpacity(max(0.1, min(opacity, 1.0)))

        screen = QGuiApplication.primaryScreen()
        geometry = screen.geometry() if screen else QRect(0, 0, 1280, 720)
        self.setGeometry(geometry)
        self._tracks = self._build_tracks(geometry.height())
        self._panel_rect = self._build_panel_rect(geometry)
        self._configure_panel_widget()
        self._panel_next_y = self.panel_widget.height()

    def _keep_on_top(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            if self.geometry() != geometry:
                self.setGeometry(geometry)
                self._tracks = self._build_tracks(geometry.height())
                self._panel_rect = self._build_panel_rect(geometry)
                self._configure_panel_widget()
        self.showFullScreen()
        self.raise_()

    def _build_panel_rect(self, geometry: QRect) -> QRect:
        width = max(160, int(geometry.width() * self.panel_width_ratio))
        height = max(120, int(geometry.height() * self.panel_height_ratio))
        left = int(geometry.width() * self.panel_left_ratio)
        top = int(geometry.height() * self.panel_top_ratio)
        if left + width > geometry.width():
            left = max(0, geometry.width() - width - 16)
        if top + height > geometry.height():
            top = max(0, geometry.height() - height - 16)
        return QRect(left, top, width, height)

    def _configure_panel_widget(self) -> None:
        self.panel_widget.setGeometry(self._panel_rect)
        self.panel_widget.setVisible(self.mode == "panel")
        self.panel_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        alpha = max(0, min(self.panel_background_alpha, 255))
        self.panel_widget.setStyleSheet(
            f"QWidget {{ background-color: rgba(0, 0, 0, {alpha}); border-radius: 6px; }}"
        )

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

        if self.mode == "panel":
            text = self.pending.popleft()
            self._spawn_panel_item(text)
            self._schedule_next_spawn()
            return

        track_y = self._choose_available_track()
        if track_y is None:
            self.spawn_timer.start(250)
            return

        text = self.pending.popleft()
        while len(self.items) >= self.max_danmaku:
            self._remove_item(self.items[0])

        label = self._create_text_label(text, self, background_alpha=self.text_background_alpha)
        label.setFont(QFont(self.font_family, self.font_size, QFont.Weight.Bold))
        label.adjustSize()

        x = self.width() + random.randint(0, 160)
        label.move(QPoint(x, track_y))
        label.show()

        speed = random.randint(self.speed_min, self.speed_max)
        self.items.append(DanmakuItem(label=label, speed=speed, track_y=track_y))
        self.recent_texts.append(text)
        self._schedule_next_spawn()

    def _spawn_panel_item(self, text: str) -> None:
        while len(self.panel_items) >= self.panel_max_items:
            self._remove_panel_item(self.panel_items[0])

        label = self._create_text_label(text, self.panel_widget, background_alpha=0)
        label.setFont(QFont(self.font_family, self.font_size, QFont.Weight.Bold))
        label.setFixedWidth(max(80, self.panel_widget.width() - 16))
        label.adjustSize()

        x = 8
        y = max(self._panel_next_y, self.panel_widget.height() - label.height())
        label.move(QPoint(x, y))
        label.show()
        self.panel_items.append(PanelItem(label=label))
        self.recent_texts.append(text)
        self._panel_next_y = y + label.height() + self.panel_line_gap

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
        if self.mode == "panel":
            self._tick_panel(dt)
            self.update(self._panel_rect)
            return

        for item in list(self.items):
            label = item.label
            label.move(int(label.x() - item.speed * dt), label.y())
            if label.x() + label.width() < 0:
                self._remove_item(item)

    def _tick_panel(self, dt: float) -> None:
        dy = max(1, int(self.panel_scroll_speed * dt))
        for item in list(self.panel_items):
            label = item.label
            label.move(label.x(), label.y() - dy)
            if label.y() + label.height() < 0:
                self._remove_panel_item(item)
        if self.panel_items:
            self._panel_next_y = max(
                self.panel_widget.height(),
                max(item.label.y() + item.label.height() for item in self.panel_items)
                + self.panel_line_gap,
            )
        else:
            self._panel_next_y = self.panel_widget.height()

    def _remove_item(self, item: DanmakuItem) -> None:
        if item in self.items:
            self.items.remove(item)
        item.label.hide()
        item.label.deleteLater()

    def _create_text_label(self, text: str, parent: QWidget, background_alpha: int) -> QLabel:
        return OutlinedLabel(
            text,
            parent,
            text_color=self.color,
            outline_color=self.outline_color,
            outline_width=self.outline_width,
            background_alpha=background_alpha,
        )

    def _remove_panel_item(self, item: PanelItem) -> None:
        if item in self.panel_items:
            self.panel_items.remove(item)
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
