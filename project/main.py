from __future__ import annotations

import argparse
import logging
import random
import re
import signal
import sys
import threading
import time
from collections import deque

from audit_log import AuditLog, NullAuditLog
from config import AppConfig, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen OCR to DeepSeek danmaku overlay")
    parser.add_argument(
        "--test-api",
        action="store_true",
        help="Test DeepSeek API configuration and exit without starting the overlay.",
    )
    return parser.parse_args()


def build_region(config: AppConfig) -> dict[str, int] | None:
    values = [config.region_left, config.region_top, config.region_width, config.region_height]
    if any(value is None for value in values):
        return None
    return {
        "left": int(config.region_left or 0),
        "top": int(config.region_top or 0),
        "width": int(config.region_width or 0),
        "height": int(config.region_height or 0),
    }


def worker_loop(
    config: AppConfig,
    bridge: OverlayBridge,
    stop_event: threading.Event,
    audit: AuditLog,
) -> None:
    from danmaku_generator import DeepSeekDanmakuGenerator
    from screen_capture import ScreenCapture
    from screen_understanding import ScreenUnderstanding

    capture = ScreenCapture(
        monitor_index=config.monitor_index,
        region=build_region(config),
        change_threshold=config.change_threshold,
    )
    understanding = ScreenUnderstanding(
        engine_name=config.ocr_engine,
        max_context_chars=config.max_context_chars,
    )
    generator = DeepSeekDanmakuGenerator(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )

    last_ocr_at = 0.0
    last_llm_at = 0.0
    last_same_context_sent_at = 0.0
    last_context = ""
    last_sent_context_key = ""
    recent_bullets: deque[str] = deque(maxlen=40)

    while not stop_event.is_set():
        loop_start = time.monotonic()
        try:
            result = capture.capture()
            now = time.monotonic()
            audit.record(
                "capture",
                result="screen image captured locally; image bytes are not uploaded",
                detail="change detection completed",
                changed=result.changed,
                diff_score=result.diff_score,
            )

            if result.changed and now - last_ocr_at >= config.ocr_interval_sec:
                last_context = understanding.understand(result.image_bgr)
                last_ocr_at = now
                audit.record(
                    "ocr",
                    collected_text=last_context,
                    result=f"{len(last_context)} chars after OCR cleanup",
                    detail=f"engine={config.ocr_engine}",
                    changed=result.changed,
                    diff_score=result.diff_score,
                )
            elif result.changed:
                audit.record(
                    "ocr_skipped",
                    collected_text=last_context,
                    result="kept previous OCR context",
                    detail="OCR interval throttle",
                    changed=result.changed,
                    diff_score=result.diff_score,
                )

            if (
                result.changed
                and last_context
                and now - last_llm_at >= config.llm_interval_sec
            ):
                context_key = _context_key(last_context)
                if (
                    context_key == last_sent_context_key
                    and now - last_same_context_sent_at < config.context_repeat_cooldown_sec
                ):
                    audit.record(
                        "llm_skipped",
                        collected_text=last_context,
                        uploaded_data="",
                        result="not uploaded",
                        detail="same OCR context within cooldown",
                        changed=result.changed,
                        diff_score=result.diff_score,
                    )
                    last_llm_at = now
                    continue

                recent_bullet_list = list(recent_bullets)
                upload_payload = generator.build_request_payload(last_context, recent_bullet_list)
                audit.record(
                    "llm_upload",
                    collected_text=last_context,
                    uploaded_data=upload_payload,
                    result="request prepared for DeepSeek",
                    detail=f"enabled={str(generator.enabled).lower()}",
                    changed=result.changed,
                    diff_score=result.diff_score,
                )
                bullets = generator.generate(last_context, recent_bullet_list)
                audit.record(
                    "llm_response",
                    collected_text=last_context,
                    result=bullets,
                    detail=f"{len(bullets)} bullets parsed",
                    changed=result.changed,
                    diff_score=result.diff_score,
                )
                if bullets:
                    random.shuffle(bullets)
                    bridge.danmaku_ready.emit(bullets)
                    audit.record(
                        "overlay_queue",
                        collected_text="\n".join(bullets),
                        result="queued for local overlay display",
                        detail=f"{len(bullets)} bullets",
                        changed=result.changed,
                        diff_score=result.diff_score,
                    )
                    recent_bullets.extend(bullets)
                    last_sent_context_key = context_key
                    last_same_context_sent_at = now
                last_llm_at = now
        except Exception:
            logging.exception("Background loop failed")
            audit.record("error", result="background loop failed", detail="see console log")

        elapsed = time.monotonic() - loop_start
        stop_event.wait(max(0.1, config.capture_interval_sec - elapsed))


def _context_key(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    return compact[:600]


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config()

    if args.test_api:
        from danmaku_generator import test_deepseek_connection_stdlib

        ok, message = test_deepseek_connection_stdlib(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
            model=config.deepseek_model,
        )
        if ok:
            print(f"DeepSeek API test passed. model={config.deepseek_model}, response={message}")
            return 0
        print(f"DeepSeek API test failed. model={config.deepseek_model}, error={message}")
        return 1

    audit: AuditLog = (
        AuditLog(
            enabled=True,
            directory=config.audit_log_dir,
            text_limit=config.audit_log_text_limit,
        )
        if config.audit_log_enabled
        else NullAuditLog()
    )
    if audit.path is not None:
        logging.info("Audit table: %s", audit.path)

    from PyQt6.QtCore import QObject, pyqtSignal

    from overlay import DanmakuOverlay, create_app

    class OverlayBridge(QObject):
        danmaku_ready = pyqtSignal(list)

    app = create_app()
    overlay = DanmakuOverlay(
        font_size=config.font_size,
        font_family=config.font_family,
        color=config.danmaku_color,
        speed_min=config.danmaku_speed_min,
        speed_max=config.danmaku_speed_max,
        spawn_interval_min_ms=config.danmaku_spawn_interval_min,
        spawn_interval_max_ms=config.danmaku_spawn_interval_max,
        area_top_ratio=config.danmaku_area_top_ratio,
        area_bottom_ratio=config.danmaku_area_bottom_ratio,
        track_gap_px=config.danmaku_track_gap_px,
        max_danmaku=config.max_danmaku,
        click_through=config.overlay_click_through,
        opacity=config.overlay_opacity,
        keep_top_interval_ms=config.overlay_keep_top_interval_ms,
    )
    overlay.showFullScreen()

    bridge = OverlayBridge()
    bridge.danmaku_ready.connect(overlay.add_danmaku_batch)

    stop_event = threading.Event()
    worker = threading.Thread(
        target=worker_loop,
        args=(config, bridge, stop_event, audit),
        name="screen-danmaku-worker",
        daemon=True,
    )
    worker.start()

    def stop(*_: object) -> None:
        stop_event.set()
        app.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    exit_code = app.exec()
    stop_event.set()
    worker.join(timeout=2)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
