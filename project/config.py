from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # Allows `python main.py --test-api` before dependencies are installed.
    load_dotenv = None

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is optional at import time.
    yaml = None


BASE_DIR = Path(__file__).resolve().parent


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _get(config: dict[str, Any], key: str, default: Any = None) -> Any:
    env_value = os.getenv(key)
    if env_value is not None:
        return env_value
    return config.get(key, default)


def _get_nonempty(config: dict[str, Any], key: str, default: Any = None) -> Any:
    value = _get(config, key, default)
    if value == "":
        return default
    return value


@dataclass(frozen=True)
class AppConfig:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str

    capture_interval_sec: float
    ocr_interval_sec: float
    llm_interval_sec: float
    change_threshold: float
    context_repeat_cooldown_sec: float

    ocr_engine: str
    max_context_chars: int

    font_size: int
    font_family: str
    danmaku_color: str
    danmaku_speed_min: int
    danmaku_speed_max: int
    danmaku_spawn_interval_min: int
    danmaku_spawn_interval_max: int
    danmaku_area_top_ratio: float
    danmaku_area_bottom_ratio: float
    max_danmaku: int
    overlay_click_through: bool
    overlay_opacity: float

    monitor_index: int
    region_left: int | None
    region_top: int | None
    region_width: int | None
    region_height: int | None

    audit_log_enabled: bool
    audit_log_dir: str
    audit_log_text_limit: int


def _load_yaml_config() -> dict[str, Any]:
    path = BASE_DIR / "config.yaml"
    if not path.exists() or yaml is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_config() -> AppConfig:
    if load_dotenv is not None:
        load_dotenv(BASE_DIR / ".env")
    else:
        _load_simple_env(BASE_DIR / ".env")
    yaml_config = _load_yaml_config()

    return AppConfig(
        deepseek_api_key=str(_get(yaml_config, "DEEPSEEK_API_KEY", "")),
        deepseek_base_url=str(_get(yaml_config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")),
        deepseek_model=str(_get(yaml_config, "DEEPSEEK_MODEL", "deepseek-chat")),
        capture_interval_sec=float(_get(yaml_config, "CAPTURE_INTERVAL_SEC", 1.0)),
        ocr_interval_sec=float(_get(yaml_config, "OCR_INTERVAL_SEC", 2.0)),
        llm_interval_sec=float(_get(yaml_config, "LLM_INTERVAL_SEC", 5.0)),
        change_threshold=float(_get(yaml_config, "CHANGE_THRESHOLD", 4.0)),
        context_repeat_cooldown_sec=float(_get(yaml_config, "CONTEXT_REPEAT_COOLDOWN_SEC", 30.0)),
        ocr_engine=str(_get(yaml_config, "OCR_ENGINE", "rapidocr")).lower(),
        max_context_chars=int(_get(yaml_config, "MAX_CONTEXT_CHARS", 1200)),
        font_size=int(_get(yaml_config, "FONT_SIZE", 28)),
        font_family=str(_get(yaml_config, "FONT_FAMILY", "Microsoft YaHei UI")),
        danmaku_color=str(_get(yaml_config, "DANMAKU_COLOR", "#FFFFFF")),
        danmaku_speed_min=int(_get(yaml_config, "DANMAKU_SPEED_MIN", 90)),
        danmaku_speed_max=int(_get(yaml_config, "DANMAKU_SPEED_MAX", 170)),
        danmaku_spawn_interval_min=int(_get(yaml_config, "DANMAKU_SPAWN_INTERVAL_MIN_MS", 650)),
        danmaku_spawn_interval_max=int(_get(yaml_config, "DANMAKU_SPAWN_INTERVAL_MAX_MS", 1600)),
        danmaku_area_top_ratio=float(_get(yaml_config, "DANMAKU_AREA_TOP_RATIO", 0.08)),
        danmaku_area_bottom_ratio=float(_get(yaml_config, "DANMAKU_AREA_BOTTOM_RATIO", 0.55)),
        max_danmaku=int(_get(yaml_config, "MAX_DANMAKU", 80)),
        overlay_click_through=_to_bool(_get(yaml_config, "OVERLAY_CLICK_THROUGH", True), True),
        overlay_opacity=float(_get(yaml_config, "OVERLAY_OPACITY", 0.92)),
        monitor_index=int(_get(yaml_config, "MONITOR_INDEX", 1)),
        region_left=_optional_int(_get(yaml_config, "REGION_LEFT", None)),
        region_top=_optional_int(_get(yaml_config, "REGION_TOP", None)),
        region_width=_optional_int(_get(yaml_config, "REGION_WIDTH", None)),
        region_height=_optional_int(_get(yaml_config, "REGION_HEIGHT", None)),
        audit_log_enabled=_to_bool(_get(yaml_config, "AUDIT_LOG_ENABLED", True), True),
        audit_log_dir=str(_get_nonempty(yaml_config, "AUDIT_LOG_DIR", str(BASE_DIR / "logs"))),
        audit_log_text_limit=int(_get(yaml_config, "AUDIT_LOG_TEXT_LIMIT", 4000)),
    )


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _load_simple_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
