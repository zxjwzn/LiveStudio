# 第一步：音频流订阅 + 本机播放 + 音频源标识

## 目标
1. 给 `AudioChunk` 加**音频源标识**，让下游订阅方能识别/过滤音频来自哪个源。
2. 新增**本机播放订阅方** `AudioPlaybackSink`：订阅音频总线（router），按源标识过滤，用 `sounddevice.OutputStream` 在本机输出设备播放。

本步**不**实现 TTS 合成（engine 仍为占位），只打通"订阅 → 过滤 → 本机播放"管道并打好源标识地基。TTS engine、MCP `speak`、打断/fade 等留作后续步骤。

## 关键设计决策

### 1. `AudioChunk.source` 字段（必填，无默认）
- 由**产出方**打标：麦克风源 `MICROPHONE`，TTS 源（将来）`TTS`。router 转发时不改写（chunk 是同一对象，原样广播）。
- 必填（无默认）：强制每个源声明自身，杜绝"无源"块。全仓库仅 2 处构造（`microphone.py:184` + 测试 helper `_make_chunk`），改动可控。
- dataclass 字段顺序：`frames, samplerate, channels, data, source, overflowed=...`（必填字段放在有默认值字段之前）。

### 2. 播放订阅方挂在 router 总线，按 `source` 过滤
- `AudioPlaybackSink` 是总线消费方（与 `AudioController` 电平表、`MouthSyncController` 唇形同构）：订阅 router，drain 队列，按 `chunk.source ∈ config.sources` 放行。
- 默认 `sources=[TTS]`（避免回放麦克风→啸叫）。测试时可临时加 `MICROPHONE` + 耳机验证管道。
- 这样设计天然支持后续"TTS 接管总线"模型：TTS chunk 带源标识，sink 自动放行播放，无需 sink 订阅特定源。

### 3. 线程模型（与麦克风源对称但反向）
- 麦克风：PortAudio 实时线程回调 → `call_soon_threadsafe` → 事件循环 `_publish_chunk`。
- 播放：事件循环 drain 订阅队列 → 转换 PCM → 推入**线程安全缓冲**（`deque` + `threading.Lock`，有界丢最旧）→ PortAudio `OutputStream` 回调在实时线程取缓冲填充，欠载填零。
- 输出流**懒开启**：首个放行 chunk 到达才开 `sd.OutputStream`；sink stop 时关闭。v1 不做空闲超时关流（保持简单；OutputStream 持有期间欠载写零）。

### 4. PCM 格式归一（sink 固定格式）
- `PlaybackConfig.samplerate`（None=输出设备默认）/`channels` 决定 OutputStream 格式。
- 每个 chunk 转 float32 → 声道 mixdown/复制到 sink channels → `np.interp` 重采样到 sink samplerate → 乘 volume。线性重采样对语音足够；soxr/scipy 留后续。

### 5. router 拥有 sink 生命周期
- sink 在 router `_do_start` 末尾起、`_do_stop` 开头停（须在 `_clear_subscriptions` 前，让其优雅退订+关流）。
- `_do_restart`（源软重启）与 `switch_source` **不碰** sink——它是总线抽头，与具体源无关，跨源切换/重启存活。
- 配置变更（输出设备/enabled/sources）经 `router.apply_playback_config()` 重建 sink。

## 文件改动清单

### 新增
- `livestudio/services/audio_stream/playback.py`
  - `PlaybackConfig(BaseModel)`：`enabled: bool=True`、`output_device: int|None=None`、`samplerate: int|None=None`、`channels: int=1`、`volume: float=1.0`、`sources: list[AudioSourceKind]=[TTS]`、`fade_out_ms: int=30`。`extra="forbid"`，`json_schema_extra={"icon":"VOLUME"}`。
  - `OutputDeviceInfo(BaseModel)`：镜像 `InputDeviceInfo`，`max_output_channels` 替换 `max_input_channels`。
  - `AudioPlaybackSink(AsyncServiceLifecycleMixin)`：构造 `(router: AudioStreamSource, config: PlaybackConfig)`。
    - `_do_start`：`router.subscribe(queue_maxsize=...)` 存订阅，起 `_drain` 任务。
    - `_drain`：循环 `await sub.queue.get()`；`if chunk.source not in config.sources: continue`；转换 PCM → 推线程安全缓冲；首个块懒开 OutputStream。
    - `_do_stop`：cancel drain → 关 OutputStream（`to_thread`）→ `router.unsubscribe` → 清缓冲。
    - `flush()`：清缓冲 + 对尾做 `fade_out_ms` 衰减（为后续打断预留；本步在 stop 时用）。
    - `list_output_devices()`：`sd.query_devices()` 过滤 `max_output_channels>0`，归一为 `OutputDeviceInfo`。
    - 内部线程安全缓冲 + `_output_callback(outdata, frames, time_info, status)` 实时线程取数。
- `tests/test_audio_playback_sink.py`：sink 过滤/生命周期/格式转换（mock `sd.OutputStream`）。

### 改动
- `livestudio/services/audio_stream/models.py`
  - `AudioChunk` 加 `source: AudioSourceKind`（必填，置于 `data` 后、`overflowed` 前）。导入 `AudioSourceKind`（同文件已定义）。
- `livestudio/services/audio_stream/config.py`
  - `AudioStreamRouterConfig` 加 `playback: PlaybackConfig = Field(default_factory=PlaybackConfig)`。导入 `PlaybackConfig`。
- `livestudio/services/audio_stream/sources/microphone/microphone.py`
  - `AudioChunk(...)` 构造加 `source=AudioSourceKind.MICROPHONE`（`microphone.py:184`）。导入 `AudioSourceKind`。
- `livestudio/services/audio_stream/service.py`（router）
  - `__init__`：加 `self._playback_sink: AudioPlaybackSink | None = None`。
  - `_do_start`：forward task 后，`if self.config.playback.enabled:` 建 sink 并 `await sink.start()`。
  - `_do_stop`：`_stop_forward_task()` 后、退订活动源前，`if self._playback_sink: await stop; =None`。
  - 新增 `list_output_devices() -> list[OutputDeviceInfo]`：复用 sink 或临时查询（与 `list_input_devices` 同风格，生命周期解耦）。
  - 新增 `apply_playback_config()`：停旧 sink → 读新 config → 建新 sink → start（若 router 已启动）。
- `livestudio/services/audio_stream/__init__.py` + `livestudio/services/__init__.py`
  - 导出 `AudioPlaybackSink`、`PlaybackConfig`、`OutputDeviceInfo`。
- `livestudio/gui/bridge/audio_bridge.py`（AudioController）
  - 加 `playbackChanged = Signal(bool)`（可选，sink 状态）。加 `playback_config()`、`save_playback_config(config)`、`list_output_device_choices()`（镜像 `list_device_choices`，输出设备）。
- `livestudio/gui/views/audio_view.py`
  - 加"本机播放" `ConfigEditor[PlaybackConfig]` 卡片，`choices_providers={"output_device": self._output_choice_items}`；`_on_playback_saved` → `save_playback_config`。
- `tests/test_audio_stream_source.py`
  - `_make_chunk` 加 `source=AudioSourceKind.MICROPHONE`。
  - 加测试：router 转发的 chunk 携带产出方源标识。
- `configs`（运行时自动生成）：`audio_stream.yaml` 增 `playback:` 段（默认值）。

## 关键代码草图

```python
# models.py
@dataclass(slots=True)
class AudioChunk:
    frames: int
    samplerate: int
    channels: int
    data: NDArray[np.generic]
    source: AudioSourceKind                 # 新增，必填
    overflowed: bool = False
    metadata: AudioChunkMetadata | None = None
    analysis: AudioChunkAnalysis = field(default_factory=AudioChunkAnalysis)

# playback.py
class AudioPlaybackSink(AsyncServiceLifecycleMixin):
    def __init__(self, router: AudioStreamSource, config: PlaybackConfig) -> None: ...
    async def _do_start(self) -> None: ...        # subscribe + 起 _drain
    async def _do_stop(self) -> None: ...         # cancel drain + 关流 + 退订
    async def _drain(self) -> None:
        while True:
            chunk = await self._sub.queue.get()
            if chunk.source not in self._config.sources:
                continue
            pcm = self._convert(chunk)            # float32/声道/重采样/volume
            self._push_buffer(pcm)                # 线程安全缓冲
            self._ensure_stream_open(chunk)
    def _output_callback(self, outdata, frames, time_info, status) -> None: ...  # 实时线程取缓冲，欠载填零
    def flush(self) -> None: ...                  # 清缓冲 + fade-out
    @staticmethod
    def list_output_devices() -> list[OutputDeviceInfo]: ...
```

## 不在本步范围
- TTS engine 实现（`tts.py` 仍占位，但会在 `_publish_chunk` 时带 `source=TTS`——本步可顺手把 TTS 占位源的"将来打标"在注释里标明，不改其行为）。
- MCP `speak`/`stop_speaking` 工具、`app.speak()`。
- speak 期间运行时转发覆盖（TTS 接管总线）。
- 打断新内容、完整 fade 包络（本步仅 stop 时 fade-out 防爆音）。
- OBS 虚拟声卡：本步选输出设备即可覆盖（用户选 VB-Cable 即 OBS 可用），无需额外代码。

## 验证
- `npx pyright` 类型自检（用户用 Pylance，禁用注释屏蔽）。
- `.venv\Scripts\python.exe -m pytest tests/test_audio_stream_source.py tests/test_audio_playback_sink.py`。
- 手动：`python -m livestudio.gui`，音频页"本机播放"卡片选输出设备、sources 临时加麦克风、戴耳机验证麦克风被本地播放；切回 `sources=[TTS]` 等待后续 TTS。
