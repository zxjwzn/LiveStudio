# TTS engine 基类 + Fish Audio 接入 + 字幕流

## 目标
1. **TTS engine 基类** `TtsEngine`:规范各 TTS 供应商接入--输入文本,流式产出(音频块 + 字幕段落),可取消。
2. **Fish Audio engine**:第一个实现,httpx 调 SSE 端点,产出 pcm 音频 + 逐词 alignment(全局时间)。
3. **字幕流** `SubtitleStream`:像音频流一样的 pub/sub(订阅/广播,丢最旧),**发送频率由发送方(engine)控制**,流本身是哑管道。网页消费端**本次不做**(后续接 WS 网页)。
4. `TTSAudioStreamSource.speak(text)`:驱动 engine,音频块发到音频总线(`_publish_chunk`),字幕段落发到 `SubtitleStream`;发声期间阻塞空闲静音(asyncio.Event);取消-前置语义。

## 设计

### 1. 字幕流(镜像音频流 pub/sub)
新模块 `livestudio/services/subtitle/stream.py`:
```python
@dataclass
class SubtitleSegment:
    text: str
    start: float  # 全局秒(chunk_audio_offset_sec 已加)
    end: float

@dataclass
class SubtitleEvent:
    kind: Literal["begin", "segments", "finish"]
    text: str | None = None            # begin: 全文(供 force-finish 显示)
    segments: list[SubtitleSegment] | None = None  # segments: 增量对齐(仅新增段)

@dataclass(frozen=True, slots=True)
class SubtitleSubscription:
    id: UUID
    queue: asyncio.Queue[SubtitleEvent]

class SubtitleStream:
    """字幕事件总线(pub/sub,镜像 AudioStreamSource)。发送方控制频率,流只扇出(丢最旧)。"""
    def subscribe(self, *, queue_maxsize=64) -> SubtitleSubscription: ...
    def unsubscribe(self, sub) -> None: ...
    def _publish(self, event) -> None: ...       # 扇出,满则丢最旧(同 _publish_chunk)
    # 生产者 API(TTS 源调用):
    def begin(self, text: str) -> None: ...       # _publish(begin, text)
    def publish_segments(self, segs) -> None: ... # _publish(segments, segs)
    def finish(self) -> None: ...                 # _publish(finish)
```
- 不做时间调度(发送方控制频率);网页(后续)自行按 segment.start 调度揭示。
- v1 无消费者:`_publish` 扇出到空订阅集 = 空操作(同音频流)。

### 2. TTS engine 基类
新模块 `livestudio/services/audio_stream/sources/tts/engines/base.py`:
```python
@dataclass
class TtsAudioOutput:
    data: NDArray[np.float32]  # (frames, channels) float32
    frames: int

@dataclass
class TtsSubtitleOutput:
    segments: list[SubtitleSegment]  # 仅新增段(已去重、全局时间)

TtsOutput = TtsAudioOutput | TtsSubtitleOutput

class TtsEngine(ABC):
    def __init__(self, *, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate; self._channels = channels
    @property
    def sample_rate(self) -> int: return self._sample_rate
    @property
    def channels(self) -> int: return self._channels
    @abstractmethod
    def synthesize(self, text: str, **opts) -> AsyncIterator[TtsOutput]: ...

def make_engine(config: FishAudioEngineConfig, *, sample_rate, channels) -> TtsEngine:
    # 按 config.kind 分发(现仅 fish_audio;加新 engine 在此分支)
    ...
```
- engine 是 async generator:`synthesize` 产出 `TtsAudioOutput | TtsSubtitleOutput`,由 TTS 源迭代分发。
- 可取消:迭代任务被 cancel 时,generator 收到 GeneratorExit,engine 在 `finally`/`async with` 里清理(httpx 流自动关)。

### 3. Fish Audio engine
`engines/fish_audio.py`:
```python
class FishAudioEngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})
    kind: Literal["fish_audio"] = "fish_audio"
    api_key: str = Field(json_schema_extra={"hidden": True})
    model: Literal["s2.1-pro-free","s2.1-pro","s2-pro","s1"] = "s2.1-pro-free"
    reference_id: str | None = Field(default=None, description="Fish Audio 声音模型 ID")
    latency: Literal["balanced","normal","low"] = "balanced"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)

class FishAudioEngine(TtsEngine):
    async def synthesize(self, text, **opts) -> AsyncIterator[TtsOutput]:
        headers = {Authorization: Bearer, model, Content-Type}
        payload = {text, format="pcm", sample_rate, latency, normalize=True,
                   temperature=0.7, top_p=0.7, chunk_length=300,
                   prosody={speed, volume=0}, reference_id?}
        async with httpx.AsyncClient(timeout=...) as client:
          async with client.stream("POST", URL, headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "): continue
                evt = json.loads(line[6:])
                # 音频:base64 -> int16 -> float32 -> (frames, channels)
                pcm = base64.b64decode(evt["audio_base64"])
                s = np.frombuffer(pcm, np.int16).astype(np.float32)/32768.0
                s = s.reshape(-1, 1) if channels==1 else np.repeat(s.reshape(-1,1), channels, 1)
                yield TtsAudioOutput(s, s.shape[0])
                # 字幕:对齐快照,去重(仅发新增段,全局时间)
                if evt.get("alignment") is not None:
                    offset = evt["chunk_audio_offset_sec"]
                    segs = [SubtitleSegment(t["text"], t["start"]+offset, t["end"]+offset) ...]
                    snapshots[evt["chunk_seq"]] = segs
                    timeline = [s for cs in sorted(snapshots) for s in snapshots[cs]]
                    new = timeline[emitted:]; emitted = len(timeline)
                    if new: yield TtsSubtitleOutput(new)
```
- **去重**:alignment 是 chunk_seq 的"最新累计快照"(后续事件更完整);按 chunk_seq 存最新,全局时间线 = 各 chunk_seq 快照按序拼接,只发射 `emitted` 之后的新增段。
- **PCM 假设**:format=pcm 即 int16 LE mono(文档未明说,需首次用真 key 验证;若不同调 `np.frombuffer` dtype)。
- httpx 已可用(mcp 传递依赖),无新依赖。

### 4. TTSAudioStreamConfig 重构
`sources/tts/config.py`:
```python
class TTSAudioStreamConfig(BaseModel):
    engine: FishAudioEngineConfig = Field(default_factory=FishAudioEngineConfig, description="TTS 引擎配置")
    samplerate: int = Field(default=24000, gt=0, json_schema_extra={"hidden": True})  # idle 静音 + engine sample_rate
    channels: int = Field(default=1, ge=1, json_schema_extra={"hidden": True})
```
- 删占位 `stream_url`/`format`(`format=pcm` 固定在 engine 实现里)。
- **迁移**:磁盘 `audio_stream.yaml` 的 `tts:` 段若有旧 `format`/`stream_url`,加载会因 `extra="forbid"` 失败--需删 `tts:` 段(或整文件)让其按新 schema 重建。(实现时确认;或保留 `format`/`stream_url` 作废弃兼容字段。)
- 暂用直字段 `engine: FishAudioEngineConfig`(非 union):单 engine 时 GUI 渲染为嵌套模型,无 awkward 单成员 union 下拉。加第二个 engine 时改为 `Annotated[Union[...], Field(discriminator="kind")]`(`make_engine` 已按 `kind` 分发,前向兼容)。

### 5. TTSAudioStreamSource.speak
`sources/tts/tts.py`:
- `__init__(config, subtitle_stream)`:存 engine(`make_engine(config.engine, sample_rate=config.samplerate, channels=config.channels)`)、subtitle_stream、`_idle_event=Event()`(set)、`_utterance_task`。
- `_do_start`:起 `_idle_loop`(改为 `await _idle_event.wait()` 后发静音,发声期间阻塞)。
- `async speak(text, **opts)`:`await stop_speaking()`(cancel+await 旧任务,其 finally 发 finish)-> `_idle_event.clear()` -> `subtitle_stream.begin(text)` -> 起 `_utterance` 任务。**async**(await 旧清理保证 finish 先于新 begin 的顺序)。
- `async stop_speaking()`:cancel + await `_utterance_task`。
- `is_speaking`:`_utterance_task` 在跑。
- `_utterance(text, **opts)`:迭代 `engine.synthesize`:`TtsAudioOutput` -> `_publish_chunk(AudioChunk(source=TTS, samplerate/channels=engine, data, frames))`;`TtsSubtitleOutput` -> `subtitle_stream.publish_segments(segs)`。`finally`(仍为当前任务时):`_idle_event.set()` + `subtitle_stream.finish()`。

### 6. 路由器拥有 SubtitleStream(跨 reload 存活)
`service.py`:
- `__init__`:`self._subtitle_stream = SubtitleStream()`(顶层,跨 TTS 源 reload 存活,保住将来网页订阅)。
- `_ensure_sources_built` / `reload_source`:`TTSAudioStreamSource(self.config.tts, self._subtitle_stream)`。
- 暴露 `@property subtitle_stream`。
- `_do_stop`:`_subtitle_stream` 不需特殊停(无任务);可在停机时清订阅(可选)。

## 配置:暴露 vs 固定
- **暴露(FishAudioEngineConfig)**:`api_key`(hidden)、`model`、`reference_id`、`latency`、`speed`。
- **固定(engine 内部)**:`format=pcm`、`sample_rate`(顶层 samplerate)、`normalize=true`、`temperature=0.7`、`top_p=0.7`、`chunk_length=300`、`prosody.volume=0`(音量归音频播放页 sink)、其余生成参数。
- 字幕流无配置(网页配置后续随 WS 网页一起加)。

## 文件
**新增**:
- `livestudio/services/subtitle/__init__.py`、`stream.py`(SubtitleStream 等)
- `livestudio/services/audio_stream/sources/tts/engines/__init__.py`、`base.py`、`fish_audio.py`
- `tests/test_subtitle_stream.py`、`tests/test_fish_audio_engine.py`(mock httpx SSE)
**改动**:
- `sources/tts/config.py`(engine 字段)、`sources/tts/tts.py`(speak + idle-event)、`service.py`(router 持有 SubtitleStream + 注入)
- 导出(`services/__init__.py` 等按需)

## 测试
- `SubtitleStream`:订阅收事件、begin/segments/finish 扇出、满队丢最旧、退订。
- `FishAudioEngine`(mock httpx `AsyncClient.stream` + 构造 SSE `data:` 行):产出 `TtsAudioOutput`(int16->float32 正确)+ `TtsSubtitleOutput`(全局时间 = start+offset,去重只发新增段)。
- `TTSAudioStreamSource.speak`(用假 engine 产出 audio+subtitle):音频块带 source=TTS 发到音频总线、字幕段发到 SubtitleStream、idle 静音发声期间阻塞、stop_speaking 取消、新 speak 取消旧(finish 先于新 begin)。
- pyright + ruff + pytest 全绿。

## 不在本步范围
- 字幕网页 / WS 服务器(`/ws/subtitles` serve HTML)--后续实现,本次只建 SubtitleStream 总线(无消费者也能跑)。
- 多 engine union(现直字段;加第二个时改 union)。
- MCP `speak`/`stop_speaking` 工具 + `app.speak()`(下一阶段;先确保 `tts_source.speak` 可用)。
- 打断新内容 fade-out、speaking 状态事件。

## 待验证假设
- Fish Audio `format=pcm` = int16 LE mono(首次真 key 跑一次确认)。
- 磁盘 `audio_stream.yaml` 的 `tts:` 段迁移(删旧字段)。
