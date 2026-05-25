# LLM Bullet Chat

[中文说明](README.zh-CN.md)

LLM Bullet Chat is a Windows desktop danmaku overlay prototype. It captures the screen locally, extracts text with OCR, redacts sensitive text on-device, asks DeepSeek to generate live-stream-style bullet comments, and displays them through a transparent always-on-top PyQt6 overlay.

The project is designed as a lightweight AI bullet-chat layer, not as a screen recording or image-upload tool. By default, screenshots stay local. Only OCR text after local privacy redaction is sent to the LLM.

## Features

- Local screen capture with change detection to avoid unnecessary OCR.
- RapidOCR as the default OCR engine, with optional PaddleOCR and EasyOCR adapters.
- DeepSeek / OpenAI-compatible Chat Completions for danmaku generation.
- Local privacy filtering before any OCR text leaves the machine.
- Floating right-to-left danmaku mode and right-side scrolling panel mode.
- Configurable font, color, outline, speed, spawn area, opacity, and maximum item count.
- Optional masking of the danmaku area before OCR to avoid reading generated comments back into the context.
- CSV audit logs for inspecting what was captured, redacted, uploaded, and generated.

## Pipeline

```text
screen capture
  -> change detection
  -> OCR text extraction
  -> local privacy redaction
  -> DeepSeek text-only request
  -> PyQt6 transparent overlay
```

Core files:

- `main.py`: application entry point and runtime loop.
- `config.py`: `.env` and optional `config.yaml` configuration loading.
- `screen_capture.py`: screen capture, change detection, and OCR mask regions.
- `screen_understanding.py`: OCR engine wrapper.
- `privacy_filter.py`: local privacy redaction.
- `danmaku_generator.py`: DeepSeek danmaku generation.
- `overlay.py`: PyQt6 transparent overlay.
- `audit_log.py`: CSV audit logging.

## Requirements

- Windows 10/11
- Python 3.10+
- DeepSeek API key

Install dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or with conda:

```powershell
conda create -n bullet-chat python=3.10
conda activate bullet-chat
pip install -r requirements.txt
```

The first RapidOCR / onnxruntime install can take a little while.

## Configuration

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least your DeepSeek API key:

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT_SEC=20.0
DANMAKU_OUTPUT_LANGUAGE=zh
```

`DANMAKU_OUTPUT_LANGUAGE` controls the generated comment language:

- `zh`: Chinese danmaku, the default.
- `en`: English danmaku, useful for English content or international streams.

The LLM prompt source is written in English. Chinese examples are stored with Unicode escapes in Python code to reduce encoding issues across Windows terminals and editors.

You can also create `config.yaml`. When the same key exists in both places, `.env` wins.

## Run

Start the overlay:

```powershell
python main.py
```

Test the DeepSeek configuration:

```powershell
python main.py --test-api
```

Test local privacy redaction:

```powershell
python main.py --test-privacy
```

Stop the app with `Ctrl+C` in the terminal, or end the Python process.

## Common Settings

### Processing cadence

```env
CAPTURE_INTERVAL_SEC=2.0
OCR_INTERVAL_SEC=4.0
LLM_INTERVAL_SEC=10.0
CHANGE_THRESHOLD=6.0
CONTEXT_REPEAT_COOLDOWN_SEC=45.0
MAX_DANMAKU=80
```

- `CAPTURE_INTERVAL_SEC`: screen capture loop interval.
- `OCR_INTERVAL_SEC`: minimum OCR interval.
- `LLM_INTERVAL_SEC`: minimum LLM request interval.
- `CHANGE_THRESHOLD`: screen-change sensitivity threshold. Higher means less sensitive.
- `CONTEXT_REPEAT_COOLDOWN_SEC`: cooldown before repeated OCR context can generate again.
- `MAX_DANMAKU`: maximum visible danmaku labels.

### Privacy filter

```env
PRIVACY_FILTER_ENGINE=regex
PRIVACY_FILTER_DEVICE=cpu
PRIVACY_FILTER_CHECKPOINT=
PRIVACY_FILTER_MAX_CHARS=1200
AUDIT_LOG_RAW_TEXT=false
```

- `regex`: default local redaction, no model download required.
- `openai`: optional local `openai/privacy-filter` model. First run may download weights.
- `none`: disables privacy filtering. Not recommended.
- `AUDIT_LOG_RAW_TEXT=false`: audit logs do not store raw OCR text by default.

Install the optional stronger privacy engine:

```powershell
pip install "opf @ git+https://github.com/openai/privacy-filter.git"
```

Then set:

```env
PRIVACY_FILTER_ENGINE=openai
PRIVACY_FILTER_DEVICE=cpu
```

If the optional engine is missing, fails to initialize, or changes its API, the app falls back to `regex` redaction.

### Danmaku style

```env
FONT_SIZE=26
FONT_FAMILY=Microsoft YaHei UI
DANMAKU_COLOR=#FFFFFF
DANMAKU_OUTLINE_COLOR=#000000
DANMAKU_OUTLINE_WIDTH=4
DANMAKU_TEXT_BACKGROUND_ALPHA=0
DANMAKU_MODE=floating
DANMAKU_SPEED_MIN=85
DANMAKU_SPEED_MAX=145
DANMAKU_SPAWN_INTERVAL_MIN_MS=800
DANMAKU_SPAWN_INTERVAL_MAX_MS=1800
DANMAKU_AREA_TOP_RATIO=0.08
DANMAKU_AREA_BOTTOM_RATIO=0.45
DANMAKU_TRACK_GAP_PX=360
DANMAKU_EXCLUDE_FROM_OCR=true
```

- `DANMAKU_MODE=floating`: right-to-left floating comments.
- `DANMAKU_MODE=panel`: right-side upward scrolling panel.
- `DANMAKU_TEXT_BACKGROUND_ALPHA`: translucent background behind each floating comment. `0` disables it.
- `DANMAKU_AREA_TOP_RATIO` / `DANMAKU_AREA_BOTTOM_RATIO`: vertical area used by floating comments.
- `DANMAKU_TRACK_GAP_PX`: minimum horizontal gap between comments on the same track.
- `DANMAKU_EXCLUDE_FROM_OCR=true`: mask the danmaku area before OCR.

Panel mode settings:

```env
DANMAKU_PANEL_LEFT_RATIO=0.70
DANMAKU_PANEL_TOP_RATIO=0.12
DANMAKU_PANEL_WIDTH_RATIO=0.28
DANMAKU_PANEL_HEIGHT_RATIO=0.55
DANMAKU_PANEL_BACKGROUND_ALPHA=70
DANMAKU_PANEL_SCROLL_SPEED=36
DANMAKU_PANEL_LINE_GAP=8
DANMAKU_PANEL_MAX_ITEMS=40
```

### Capture region

By default, the app captures the full `MONITOR_INDEX=1` screen. `0` usually means the combined all-monitor region, depending on mss monitor enumeration.

```env
MONITOR_INDEX=1
REGION_LEFT=
REGION_TOP=
REGION_WIDTH=
REGION_HEIGHT=
```

To capture a specific region, set all four `REGION_*` values:

```env
REGION_LEFT=0
REGION_TOP=0
REGION_WIDTH=1280
REGION_HEIGHT=720
```

### Overlay behavior

```env
OVERLAY_CLICK_THROUGH=true
OVERLAY_OPACITY=0.92
OVERLAY_KEEP_TOP_INTERVAL_MS=2000
```

- `OVERLAY_CLICK_THROUGH=true`: tries to let mouse input pass through the overlay.
- `OVERLAY_KEEP_TOP_INTERVAL_MS`: periodically re-applies topmost state. Set `0` to disable it.
- For overlay debugging, use `OVERLAY_CLICK_THROUGH=false` so the window can be selected.

## OCR Engines

Default:

```env
OCR_ENGINE=rapidocr
```

Optional:

```env
OCR_ENGINE=paddleocr
OCR_ENGINE=easyocr
```

Install the matching package before switching:

```powershell
pip install paddleocr
# or
pip install easyocr
```

RapidOCR is recommended for the MVP because it is the lightest setup path.

## Privacy Boundary

By default:

- Screenshots are used locally for change detection and OCR.
- DeepSeek receives only redacted OCR text and recent danmaku text.
- `.env` is ignored by Git.
- `logs/` is ignored by Git.
- Audit logs do not record raw OCR text.

Review the risk before setting `PRIVACY_FILTER_ENGINE=none` or `AUDIT_LOG_RAW_TEXT=true`.

## Windows Notes

- Desktop apps and borderless-windowed fullscreen are the best targets for overlay.
- Exclusive fullscreen games may draw above normal desktop overlays.
- Some anti-cheat, protected capture, or GPU combinations may affect transparent topmost windows.
- If comments are hard to read, increase `DANMAKU_OUTLINE_WIDTH` or set `DANMAKU_TEXT_BACKGROUND_ALPHA=60`.

## License And Dependencies

This project uses public Python packages and public APIs:

- `mss`: screen capture.
- `RapidOCR` / `onnxruntime`: local OCR.
- `PyQt6`: transparent always-on-top overlay.
- `openai-python`: OpenAI-compatible API client.
- `DeepSeek API`: text generation.
- Optional `openai/privacy-filter`: stronger local PII detection and redaction.

PyQt6 is GPL/commercial licensed. If you plan to distribute a closed-source commercial build, evaluate a commercial Qt license or a suitable alternative binding.

## Roadmap

- Add tray icon and hotkey controls.
- Support separate monitor selection for capture and overlay.
- Add local caching to reduce repeated LLM calls for the same context.
- Add more danmaku themes and presets.
- Optional visual caption support with low-frequency calls and explicit privacy boundaries.
