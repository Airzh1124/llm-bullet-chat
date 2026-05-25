# LLM Bullet Chat

LLM Bullet Chat 是一个 Windows 桌面弹幕 overlay 原型：它会本地截取屏幕、用 OCR 提取文字上下文、先做本地隐私脱敏，然后调用 DeepSeek 生成类似直播间观众的中文弹幕，并通过 PyQt6 透明置顶窗口显示在屏幕上。

这个项目的目标是做一个轻量的 AI 弹幕层，而不是录屏或视觉上传工具。默认流程只会把 OCR 后的文本上下文发给 LLM，不会上传截图图像。

## 功能

- 本地屏幕捕获和变化检测，避免无意义的高频 OCR。
- RapidOCR 默认 OCR 引擎，可按需切换 PaddleOCR 或 EasyOCR。
- DeepSeek / OpenAI-compatible Chat Completions 生成弹幕。
- 本地隐私过滤，默认用 regex 脱敏邮箱、手机号、证件号、银行卡号、API key、URL 等常见敏感信息。
- 两种弹幕模式：横向漂浮弹幕和右侧滚动面板。
- 可配置弹幕速度、区域、字体、颜色、描边、透明度和最大数量。
- 默认把弹幕区域从 OCR 检测中排除，避免弹幕被读回去形成反馈循环。
- CSV audit log 记录处理链路，方便确认“采集了什么、上传了什么、生成了什么”。

## 工作流

```text
screen capture
  -> change detection
  -> OCR text extraction
  -> local privacy redaction
  -> DeepSeek text-only request
  -> PyQt6 transparent overlay
```

主要模块：

- `main.py`: 程序入口，负责调度截屏、OCR、隐私过滤、LLM 和 overlay。
- `config.py`: 从 `.env` 和可选 `config.yaml` 读取配置。
- `screen_capture.py`: 屏幕捕获、画面变化检测、OCR mask 区域处理。
- `screen_understanding.py`: OCR 引擎封装。
- `privacy_filter.py`: 本地隐私过滤。
- `danmaku_generator.py`: DeepSeek 弹幕生成器。
- `overlay.py`: PyQt6 透明弹幕层。
- `audit_log.py`: CSV 审计日志。

## 环境要求

- Windows 10/11
- Python 3.10+
- DeepSeek API key

推荐在虚拟环境里安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果你使用 conda：

```powershell
conda create -n bullet-chat python=3.10
conda activate bullet-chat
pip install -r requirements.txt
```

首次安装 RapidOCR / onnxruntime 可能会比较慢。

## 配置

复制配置模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填写 DeepSeek API key：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT_SEC=20.0
DANMAKU_OUTPUT_LANGUAGE=zh
```

`DANMAKU_OUTPUT_LANGUAGE` 控制生成弹幕的语言：

- `zh`: 中文弹幕，默认选项。
- `en`: 英文弹幕，适合英文内容或海外直播场景。

源码里的 LLM prompt 使用英文编写，中文示例用 Unicode escape 保存，减少 Windows 终端和编辑器编码差异带来的乱码问题。

也可以创建 `config.yaml`。同名字段同时存在时，`.env` 优先。

## 运行

启动弹幕 overlay：

```powershell
python main.py
```

测试 DeepSeek 配置：

```powershell
python main.py --test-api
```

测试本地隐私过滤：

```powershell
python main.py --test-privacy
```

关闭方式：在运行窗口按 `Ctrl+C`，或结束对应 Python 进程。

## 常用配置

### 处理频率

```env
CAPTURE_INTERVAL_SEC=2.0
OCR_INTERVAL_SEC=4.0
LLM_INTERVAL_SEC=10.0
CHANGE_THRESHOLD=6.0
CONTEXT_REPEAT_COOLDOWN_SEC=45.0
MAX_DANMAKU=80
```

- `CAPTURE_INTERVAL_SEC`: 截屏循环间隔。
- `OCR_INTERVAL_SEC`: OCR 最小间隔。
- `LLM_INTERVAL_SEC`: LLM 调用最小间隔。
- `CHANGE_THRESHOLD`: 画面变化阈值，越大越不敏感。
- `CONTEXT_REPEAT_COOLDOWN_SEC`: OCR 文本几乎不变时，允许再次生成弹幕前的冷却时间。
- `MAX_DANMAKU`: 屏幕上保留的最大弹幕 label 数。

### 隐私过滤

```env
PRIVACY_FILTER_ENGINE=regex
PRIVACY_FILTER_DEVICE=cpu
PRIVACY_FILTER_CHECKPOINT=
PRIVACY_FILTER_MAX_CHARS=1200
AUDIT_LOG_RAW_TEXT=false
```

- `regex`: 默认本地脱敏，不需要下载模型。
- `openai`: 使用可选的 `openai/privacy-filter` 本地模型，首次运行可能下载权重。
- `none`: 关闭隐私过滤，不推荐。
- `AUDIT_LOG_RAW_TEXT=false`: 审计日志默认不写入原始 OCR 文本。

安装增强隐私过滤引擎：

```powershell
pip install "opf @ git+https://github.com/openai/privacy-filter.git"
```

然后修改：

```env
PRIVACY_FILTER_ENGINE=openai
PRIVACY_FILTER_DEVICE=cpu
```

如果增强引擎未安装、初始化失败或接口变化，程序会回退到 `regex` 脱敏。

### 弹幕样式

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

- `DANMAKU_MODE=floating`: 从右向左漂浮弹幕。
- `DANMAKU_MODE=panel`: 右侧面板内向上滚动。
- `DANMAKU_TEXT_BACKGROUND_ALPHA`: floating 模式下每条弹幕后方的半透明黑底，`0` 表示关闭。
- `DANMAKU_AREA_TOP_RATIO` / `DANMAKU_AREA_BOTTOM_RATIO`: floating 模式弹幕出现的垂直区域。
- `DANMAKU_TRACK_GAP_PX`: 同一轨道两条弹幕之间的最小水平间隔。
- `DANMAKU_EXCLUDE_FROM_OCR=true`: OCR 前遮掉弹幕区域，避免弹幕被识别回去。

panel 模式还可以配置：

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

### 截屏区域

默认截取 `MONITOR_INDEX=1` 的整个屏幕。`0` 通常表示所有显示器合并区域，具体取决于 mss 的显示器枚举。

```env
MONITOR_INDEX=1
REGION_LEFT=
REGION_TOP=
REGION_WIDTH=
REGION_HEIGHT=
```

如需指定区域，四个 `REGION_*` 字段必须同时填写：

```env
REGION_LEFT=0
REGION_TOP=0
REGION_WIDTH=1280
REGION_HEIGHT=720
```

### Overlay 行为

```env
OVERLAY_CLICK_THROUGH=true
OVERLAY_OPACITY=0.92
OVERLAY_KEEP_TOP_INTERVAL_MS=2000
```

- `OVERLAY_CLICK_THROUGH=true`: 尽量让鼠标点击穿透 overlay。
- `OVERLAY_KEEP_TOP_INTERVAL_MS`: 周期性重新置顶，对无边框窗口化全屏更稳定；设为 `0` 可关闭。
- 调试 overlay 时建议先设 `OVERLAY_CLICK_THROUGH=false`，否则窗口不容易被鼠标选中。

## 切换 OCR 引擎

默认：

```env
OCR_ENGINE=rapidocr
```

可选：

```env
OCR_ENGINE=paddleocr
OCR_ENGINE=easyocr
```

切换前需要安装对应依赖：

```powershell
pip install paddleocr
# or
pip install easyocr
```

MVP 阶段推荐先使用 RapidOCR，部署最轻。

## 隐私边界

默认情况下：

- 截图只在本地用于变化检测和 OCR。
- DeepSeek 请求只包含脱敏后的 OCR 文本和最近弹幕文本。
- `.env` 不会被 Git 提交。
- `logs/` 不会被 Git 提交。
- 审计日志默认不记录原始 OCR 文本。

如果把 `PRIVACY_FILTER_ENGINE=none` 或 `AUDIT_LOG_RAW_TEXT=true`，请确认你理解对应风险。

## Windows 注意事项

- 普通桌面应用和无边框窗口化全屏通常更适合 overlay。
- 独占全屏游戏可能会盖住普通桌面 overlay。
- 部分反作弊、录屏保护或显卡组合可能影响透明置顶窗口。
- 如果弹幕看不清，优先调大 `DANMAKU_OUTLINE_WIDTH`，或设置 `DANMAKU_TEXT_BACKGROUND_ALPHA=60`。

## 许可与依赖说明

本项目主要依赖公开 Python 包和公开 API：

- `mss`: 屏幕捕获。
- `RapidOCR` / `onnxruntime`: 本地 OCR。
- `PyQt6`: 透明置顶 overlay。
- `openai-python`: OpenAI-compatible API client。
- `DeepSeek API`: 弹幕文本生成。
- 可选 `openai/privacy-filter`: 本地 PII 识别与脱敏增强。

PyQt6 采用 GPL/commercial 授权。如果未来要做闭源商业分发，请评估商业授权或切换到合适授权的 Qt 绑定。

## Roadmap

- 增加 tray icon 和快捷键开关。
- 支持多显示器 capture 与 overlay 分别选择。
- 增加本地缓存，减少相同上下文重复调用 LLM。
- 增加更多弹幕主题和预设。
- 可选接入视觉 caption，但保持低频和明确隐私边界。
