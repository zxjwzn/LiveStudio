# LiveStudio

一个面向虚拟形象（VTuber）的实时驱动工具：采集音频、解算表情/动作，并通过 VTube Studio 公开 API 驱动模型参数。

## 环境要求

- Python 3.10+（见 `.python-version`）
- 依赖管理使用 [uv](https://github.com/astral-sh/uv)

## 安装

```bash
uv sync
```

依赖会安装到项目本地虚拟环境 `.venv/`。

## 运行

### 命令行（音频流监听）

```bash
# Windows
.venv\Scripts\python.exe main.py
```

启动后会监听默认麦克风并实时显示音量电平，按 `Ctrl+C` 退出。


## 配置

运行时配置位于 `configs/` 目录，按需自动创建：

- `audio_stream.yaml` —— 音频源（麦克风 / TTS）与缓冲队列配置
- `models/vtubestudio/<模型>.yaml` —— 各 VTube Studio 模型的语义动作绑定、表情等模型级配置

VTube Studio 认证令牌在首次授权后写入客户端配置，后续启动自动复用。

## 日志

默认日志级别为 `INFO`，可通过环境变量覆盖：

```bash
# Windows PowerShell
$env:LIVESTUDIO_LOG_LEVEL="DEBUG"; .venv\Scripts\python.exe main.py
```

## 开发

```bash
# 运行测试
.venv\Scripts\python.exe -m pytest

# 代码检查与格式化（统一使用 ruff）
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format .
```
