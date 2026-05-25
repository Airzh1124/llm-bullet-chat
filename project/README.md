# Screen Danmaku MVP

Windows 桌面 MVP：实时截屏，OCR 提取屏幕文字，把文字上下文发给 DeepSeek API 生成模拟直播弹幕，再用 PyQt6 透明置顶 overlay 从右往左显示。

## 调研总结与参考

本项目优先使用 pip 可安装库的公开 API，没有整段复制外部 GitHub 代码。

| 参考项目 / 库 | License | 解决的问题 | 使用方式 |
| --- | --- | --- | --- |
| [BoboTiG/python-mss](https://github.com/BoboTiG/python-mss) | MIT | Windows 屏幕截图 | 使用 `mss().grab(monitor)` 的公开 API，并用 numpy/OpenCV 转换图像 |
| [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) | Apache-2.0 | 本地 OCR | 使用 `RapidOCR()` Python API，默认 OCR 引擎 |
| [PyQt6](https://pypi.org/project/PyQt6/) / Qt Window Flags | GPL/commercial | 透明、置顶、无边框、尽量鼠标穿透 overlay | 使用 Qt 自带 `FramelessWindowHint`、`WindowStaysOnTopHint`、`WindowTransparentForInput` 等能力 |
| PyQt QLabel/QTimer 常见动画思路 | 视具体示例而定 | 弹幕移动动画 | 只借鉴“定时器更新 label 坐标”的思路，代码自行实现 |
| [DeepSeek API Docs](https://api-docs.deepseek.com/) | 文档 | OpenAI-compatible LLM 调用 | 使用 `openai.OpenAI(api_key, base_url)` 调用 DeepSeek |
| [openai-python](https://github.com/openai/openai-python) | Apache-2.0 | OpenAI-compatible client | 使用 SDK 公开 API，不复制源码 |
| [openai/privacy-filter](https://github.com/openai/privacy-filter) | Apache-2.0 | 本地 PII/隐私识别与打码 | 可选增强引擎；默认先使用本项目内置 regex 脱敏，安装 OPF 后可切换 |

PyQt6 采用 GPL/commercial 授权，适合个人/MVP/内部实验时通常问题不大；如果未来要闭源商用，建议评估商业授权或改成 LGPL 的 PySide6。

## 设计方案

数据流：

```text
mss 截屏 -> 缩略灰度图变化检测 -> RapidOCR 提取文字 -> 清洗上下文
-> 本地隐私过滤/脱敏 -> DeepSeek 生成 JSON 弹幕 -> PyQt6 overlay 显示
```

模块接口：

- `screen_capture.py`：`ScreenCapture.capture()` 返回截图、是否变化、差异分数。
- `screen_understanding.py`：`OcrEngine` 抽象接口，默认 `RapidOcrEngine`，也预留 `PaddleOcrEngine`、`EasyOcrEngine`。
- `danmaku_generator.py`：`DanmakuGenerator` 抽象接口，默认 `DeepSeekDanmakuGenerator`。
- `overlay.py`：`DanmakuOverlay.add_danmaku()` / `add_danmaku_batch()`。
- `main.py`：Qt 主线程跑 overlay，后台线程按节流间隔做截屏、OCR、LLM。

不会把截图上传给 DeepSeek，只发送 OCR 后的屏幕文字上下文。
默认还会先对 OCR 文字做本地隐私脱敏，命中的邮箱、手机号、身份证号、账号/银行卡号、API key、URL 等会替换为 `[REDACTED:...]` 后再进入 DeepSeek 请求。

## 安装

建议 Python 3.10+，Windows PowerShell：

```powershell
cd D:\Han\bullet_chat\project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

第一次安装 RapidOCR / onnxruntime 可能稍慢。

## 配置 DeepSeek

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT_SEC=20.0
```

也可以创建 `config.yaml`，同名字段会被 `.env` 覆盖。

## 运行

```powershell
python main.py
```

启动 overlay 前，可以先测试 DeepSeek 配置：

```powershell
python main.py --test-api
```

也可以单独测试本地隐私脱敏：

```powershell
python main.py --test-privacy
```

关闭方式：在运行窗口按 `Ctrl+C`，或从任务管理器结束 Python 进程。

## 调整弹幕频率

主要改 `.env`：

```env
CAPTURE_INTERVAL_SEC=2.0
OCR_INTERVAL_SEC=4.0
LLM_INTERVAL_SEC=10.0
CHANGE_THRESHOLD=6.0
CONTEXT_REPEAT_COOLDOWN_SEC=45.0
MAX_DANMAKU=80
```

- `LLM_INTERVAL_SEC`：DeepSeek 调用节流，默认约 10 秒。
- `DEEPSEEK_TIMEOUT_SEC`：DeepSeek 请求超时，避免 API 等太久导致弹幕管道停住。
- `CHANGE_THRESHOLD`：画面变化阈值，越大越不敏感，越小越容易触发。
- `CONTEXT_REPEAT_COOLDOWN_SEC`：OCR 文字几乎没变时，多久之后才允许再次生成。
- `MAX_DANMAKU`：屏幕上最多保留的弹幕 label 数。

## 隐私过滤

默认配置：

```env
PRIVACY_FILTER_ENGINE=regex
PRIVACY_FILTER_DEVICE=cpu
PRIVACY_FILTER_CHECKPOINT=
PRIVACY_FILTER_MAX_CHARS=1200
AUDIT_LOG_RAW_TEXT=false
```

- `regex`：本地正则脱敏，不需要额外下载模型，默认开启。会处理常见邮箱、手机号、身份证号、长账号/银行卡号、API key、Bearer token、URL 等。
- `openai`：使用 OpenAI 开源的 [privacy-filter](https://github.com/openai/privacy-filter) 本地模型。需要额外安装，首次运行可能下载模型权重。
- `none`：关闭隐私过滤，不建议。
- `PRIVACY_FILTER_MAX_CHARS`：OPF 每次处理的最大 OCR 文本长度，超出的部分使用 regex 兜底，避免长文本拖慢实时循环。
- `AUDIT_LOG_RAW_TEXT=false`：审计日志默认不写入原始 OCR 文本，只记录脱敏后的文本和命中摘要。

安装 OpenAI Privacy Filter 增强引擎：

```powershell
conda activate bullet_chat
pip install "opf @ git+https://github.com/openai/privacy-filter.git"
```

然后改 `.env`：

```env
PRIVACY_FILTER_ENGINE=openai
PRIVACY_FILTER_DEVICE=cpu
```

如果 OpenAI Privacy Filter 未安装、初始化失败或接口变化，程序会自动回退到 `regex` 脱敏，不会因此把未脱敏文本发给 DeepSeek。

## 调整弹幕位置和格式

这些配置可以直接改 `.env`：

```env
FONT_SIZE=26
FONT_FAMILY=Microsoft YaHei UI
DANMAKU_COLOR=#FFFFFF
DANMAKU_MODE=floating
DANMAKU_SPEED_MIN=85
DANMAKU_SPEED_MAX=145
DANMAKU_SPAWN_INTERVAL_MIN_MS=800
DANMAKU_SPAWN_INTERVAL_MAX_MS=1800
DANMAKU_AREA_TOP_RATIO=0.08
DANMAKU_AREA_BOTTOM_RATIO=0.45
DANMAKU_TRACK_GAP_PX=360
DANMAKU_PANEL_LEFT_RATIO=0.70
DANMAKU_PANEL_TOP_RATIO=0.12
DANMAKU_PANEL_WIDTH_RATIO=0.28
DANMAKU_PANEL_HEIGHT_RATIO=0.55
DANMAKU_PANEL_BACKGROUND_ALPHA=70
DANMAKU_PANEL_SCROLL_SPEED=36
DANMAKU_PANEL_LINE_GAP=8
DANMAKU_PANEL_MAX_ITEMS=40
```

- `FONT_SIZE`：字体大小。
- `FONT_FAMILY`：字体名，例如 `Microsoft YaHei UI`。
- `DANMAKU_COLOR`：CSS 颜色，如 `#FFFFFF`、`#FFD166`。
- `DANMAKU_MODE`：`floating` 为自由从右往左飘；`panel` 为右侧窗口内向上滚动。
- `DANMAKU_SPEED_MIN/MAX`：弹幕横向速度，越大越快。
- `DANMAKU_SPAWN_INTERVAL_MIN/MAX_MS`：批量生成后，逐条出现的随机间隔。
- `DANMAKU_AREA_TOP_RATIO` / `BOTTOM_RATIO`：弹幕出现的垂直区域，按屏幕高度比例计算。`0.08` 到 `0.45` 表示只在屏幕 8% 到 45% 的高度范围内出现。
- `DANMAKU_TRACK_GAP_PX`：同一轨道两条弹幕之间的最小水平间隔。仍有重叠时调大，例如 `480`；弹幕太稀疏时调小。
- `DANMAKU_PANEL_LEFT/TOP/WIDTH/HEIGHT_RATIO`：`panel` 模式的窗口位置和大小，按屏幕比例计算。
- `DANMAKU_PANEL_BACKGROUND_ALPHA`：`panel` 背景透明度，`0` 完全透明，`255` 不透明。
- `DANMAKU_PANEL_SCROLL_SPEED`：`panel` 模式向上滚动速度，越大越快。
- `DANMAKU_PANEL_MAX_ITEMS`：`panel` 模式最多保留的文本条数。

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

如果切换，需要额外安装对应依赖：

```powershell
pip install paddleocr
# 或
pip install easyocr
```

MVP 推荐先用 RapidOCR，部署最轻。

## 指定截图区域

默认截取 `MONITOR_INDEX=1` 的整个屏幕。可填写区域：

```env
REGION_LEFT=0
REGION_TOP=0
REGION_WIDTH=1280
REGION_HEIGHT=720
```

四个字段必须同时填写才会生效。

## Windows Overlay 注意事项

- `OVERLAY_CLICK_THROUGH=true` 会启用 Qt 的鼠标穿透窗口 flag，通常能让鼠标点到下面的窗口。
- `OVERLAY_KEEP_TOP_INTERVAL_MS=2000` 会周期性把 overlay 重新置顶；对无边框窗口/窗口化全屏更稳，设为 `0` 可关闭。
- 某些 Windows / Qt / 显卡组合下，穿透或全屏置顶行为可能不稳定。
- 如果需要调试 overlay，先设置 `OVERLAY_CLICK_THROUGH=false`，否则窗口无法被鼠标选中。
- PyQt6 overlay 使用透明无边框置顶窗口，可能被部分游戏、全屏独占程序或反作弊系统拦截。
- 如果游戏使用“独占全屏”，普通桌面 overlay 通常无法显示在游戏上方。请优先把游戏显示模式切到“无边框窗口”“窗口化全屏”或“Borderless Windowed”。

## TODO

- 加入视觉模型 caption：把 `ScreenUnderstanding` 替换成截图 caption 接口，但仍避免高频上传。
- 支持多显示器 overlay 与 capture 独立选择。
- 加入弹幕颜色、描边、轨道避让。
- 加入本地缓存，避免相同屏幕上下文重复调用 LLM。
- 增加 tray icon 和快捷键开关。
