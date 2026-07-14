"""平台应用编排基类

把「连接 → 加载模型 → 刷新控制器 → 广播变更」这套各平台都一样的编排骨架收敛到一处,
平台特有步骤(订阅何种事件、如何读当前模型、如何同步平台原生态、构建哪些控制器)留给
子类以钩子方法填充。新增平台只需继承本类实现少量抽象钩子,无需重抄生命周期与刷新流程。

模板方法模式:本类定稳调用次序与异常隔离,子类只关心「这一步在本平台上具体怎么做」。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Generic, TypeVar

from livestudio.services.animations import AnimationManager
from livestudio.services.animations.constants import EXPRESSION_CONTROLLER, TTS_SPEAK_CONTROLLER
from livestudio.services.animations.controllers import AnimationType
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.expression.models import EmotionKind
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.performance import AppPerformanceHost, PerformanceService
from livestudio.services.platforms import PlatformModelConfig, PlatformService
from livestudio.utils.log import logger

# play_emotion: 未传 hold_duration 时用配置;显式 None 表示无限保持(时间线 end 释放)
_HOLD_UNSPECIFIED: object = object()


@dataclass(frozen=True, slots=True)
class ControllerStatus:
    """一个待机动画控制器的运行态快照(供上层消费者展示/决策)"""

    name: str  # 控制器内部名(如 "blink"),启停时回传
    running: bool  # 当前是否运行中

# 模型变更监听器：参数为 (model_id, model_name)。后端只负责广播「模型已就绪/已切换」，
# 不关心由谁消费——GUI 适配器等外部观察者据此自我刷新，从而与本应用解耦。
ModelChangedListener = Callable[[str, str], Awaitable[None] | None]


class PlatformStateKind(Enum):
    """平台运行态变更种类(供上层观察者同步 GUI 等外部态)。

    后端为单一事实源:GUI 按钮与 MCP 工具都经 app 公开方法变更态,后端据此广播,GUI
    桥接订阅后 emit Qt 信号--两条路径驱动的变更都能反映到界面(MCP 不再因绕过 bridge
    而让 GUI 停留在旧态,诱发重复连接/重复运行控制器)。
    """

    CONNECTED = auto()  # 平台已连接并加载模型
    DISCONNECTED = auto()  # 平台已断开(待机控制器随之停止)
    CONTROLLERS_STARTED = auto()  # 待机动画控制器整体已启动
    CONTROLLERS_STOPPED = auto()  # 待机动画控制器整体已停止
    CONTROLLER_CHANGED = auto()  # 单个控制器运行态变更
    NATIVE_EXPRESSION_CHANGED = auto()  # 单个原生表情激活态变更(如 VTS exp3)


@dataclass(frozen=True, slots=True)
class PlatformStateEvent:
    """一次平台运行态变更:种类 + (CONTROLLER_CHANGED/NATIVE_EXPRESSION_CHANGED)名与态。

    name/active 为通用载荷:CONTROLLER_CHANGED 时 active 即「是否运行」,
    NATIVE_EXPRESSION_CHANGED 时 active 即「是否激活」。其余种类不附带载荷。
    """

    kind: PlatformStateKind
    name: str | None = None
    active: bool | None = None

    @classmethod
    def controller(cls, name: str, running: bool) -> PlatformStateEvent:
        """构造单个控制器运行态变更事件。"""

        return cls(PlatformStateKind.CONTROLLER_CHANGED, name=name, active=running)

    @classmethod
    def native_expression(cls, name: str, active: bool) -> PlatformStateEvent:
        """构造单个原生表情激活态变更事件。"""

        return cls(PlatformStateKind.NATIVE_EXPRESSION_CHANGED, name=name, active=active)


# 平台运行态监听器:参数为变更事件。同步或异步监听器都支持,异常隔离不影响主流程。
StateChangeListener = Callable[[PlatformStateEvent], Awaitable[None] | None]

TPlatform = TypeVar("TPlatform", bound=PlatformService)
TModelConfig = TypeVar("TModelConfig", bound=PlatformModelConfig)


class BasePlatformApp(AsyncServiceLifecycleMixin, ABC, Generic[TPlatform, TModelConfig]):
    """平台应用编排骨架:把平台服务、音频流与动画运行流程串起来。

    生命周期与「模型刷新」流程在本类定稳,子类只实现平台特有钩子:

    - ``_subscribe_model_events`` —— 订阅本平台的模型加载/切换事件。
    - ``_load_active_model_config`` —— 读取当前已加载模型并触发一次刷新。
    - ``_reload_model_config`` —— 按模型身份重建并返回模型级配置。
    - ``_apply_model_config`` —— 把模型配置应用到动画运行流程(构建/复用控制器)。
    - ``_sync_native_state`` —— (可选)同步平台原生态(如 VTS exp3 表情开关),默认空操作。
    - ``_on_disconnected`` —— (可选)断开后复位平台特有内部态(如事件订阅句柄),默认空操作。
    """

    def __init__(
        self,
        *,
        platform: TPlatform,
        animation_manager: AnimationManager,
        audio_stream: AudioStreamSource,
    ) -> None:
        self.platform = platform
        self.audio_stream = audio_stream
        self.animation_manager = animation_manager
        self.animation_manager.register_runtime(self.platform)
        self._model_changed_listener: ModelChangedListener | None = None
        self._state_changed_listener: StateChangeListener | None = None
        # 表演时间线(草稿+队列);host 延迟绑定 self,方法在类定义后可用
        self.performance = PerformanceService(AppPerformanceHost(self))

    def set_model_changed_listener(self, listener: ModelChangedListener | None) -> None:
        """注册模型变更监听器（首次加载与运行时换模型都会触发）。

        传 None 解除监听。监听器异常被隔离，不影响模型加载主流程。
        """

        self._model_changed_listener = listener

    def set_state_changed_listener(self, listener: StateChangeListener | None) -> None:
        """注册平台运行态变更监听器(connect/disconnect/控制器启停等都会触发)。

        传 None 解除监听。监听器异常被隔离,不影响主流程。GUI 桥接据此同步连接徽标/
        控制器开关,使 MCP 等非 GUI 调用方驱动的变更也能反映到界面。
        """

        self._state_changed_listener = listener

    async def _do_start(self) -> None:
        """启动平台相关应用（含资源准备）。

        启动失败的回滚交由 Mixin 的 start() 统一调用 stop()（即 _do_stop）。
        """

        await self.platform.start()
        await self.load_current_model()
        await self.animation_manager.start()

    async def _do_stop(self) -> None:
        """停止应用并释放资源"""

        await self.performance.shutdown()
        await self.animation_manager.stop()
        await self.platform.stop()
        self._on_disconnected()

    async def connect(self) -> None:
        """连接平台并加载当前模型，但不启动动画控制器。

        供 GUI 把「连接」与「控制器启停」拆成两个独立动作:连接只建立平台会话与
        模型配置,动画待机由 start_controllers 单独开启。
        """

        await self.platform.start()
        await self.load_current_model()
        await self._notify_state(PlatformStateEvent(PlatformStateKind.CONNECTED))

    async def disconnect(self) -> None:
        """断开平台:先停动画控制器,再停平台(镜像 _do_stop 顺序)。"""

        await self.performance.shutdown()
        await self.animation_manager.stop()
        await self.platform.stop()
        self._on_disconnected()
        await self._notify_state(PlatformStateEvent(PlatformStateKind.DISCONNECTED))

    async def start_controllers(self) -> None:
        """启动动画控制器(待机动画)。需平台已连接。"""

        await self.animation_manager.start()
        await self._notify_state(PlatformStateEvent(PlatformStateKind.CONTROLLERS_STARTED))

    async def stop_controllers(self) -> None:
        """停止动画控制器(幂等,未运行时为空操作)。"""

        await self.animation_manager.stop()
        await self._notify_state(PlatformStateEvent(PlatformStateKind.CONTROLLERS_STOPPED))

    # --- 平台无关语义动作(供 GUI / MCP 等上层消费者直接调用,不下探 runtime/platform) ---

    @property
    def current_model(self) -> tuple[str, str] | None:
        """返回当前已加载模型的 (model_id, model_name);未连接/未加载模型时为 None。

        收敛上层「读当前模型身份」的需求:此前消费者直接访问 platform.current_model 并自行
        捕获 RuntimeError,这里统一为可空返回,免去越界与异常处理。
        """

        try:
            identity = self.platform.current_model
        except RuntimeError:
            return None
        return identity.model_id, identity.model_name

    def list_controllers(self) -> list[ControllerStatus]:
        """列出当前可独立启停的待机控制器及其运行态;未连接/未加载模型时为空。

        控制器实例在「连接并加载模型」后才由 _apply_model_config 建出,故未就绪时
        runtime.controllers 为空,这里返回空列表。一次性控制器(expression)不在此列。
        """

        runtime = self.animation_manager.get_runtime(self.platform.name)
        statuses: list[ControllerStatus] = []
        for name, controller in runtime.controllers.items():
            if controller.animation_type is not AnimationType.IDLE:
                continue
            statuses.append(
                ControllerStatus(name=name, running=controller.is_running)
            )
        return statuses

    async def set_controller(self, name: str, running: bool) -> bool:
        """启停单个待机控制器(仅运行态,不改模型配置),返回操作后该控制器是否运行中。

        running=True 时启动(已在运行则幂等);running=False 时停止(幂等)。
        控制器不存在时抛 KeyError,由调用方处理。
        """

        runtime = self.animation_manager.get_runtime(self.platform.name)
        if running:
            await runtime.start_controller(name)
        else:
            await runtime.stop_controller(name)
        actual = runtime.get_controller(name).is_running
        await self._notify_state(PlatformStateEvent.controller(name, actual))
        return actual

    def available_emotions(self) -> list[str]:
        """返回可触发的情绪标识列表(EmotionKind 值,如 "joy"/"anger"/...)。

        情绪解算为平台通用能力,清单与连接态无关,恒定返回全部 EmotionKind。
        """

        return [kind.value for kind in EmotionKind]

    async def play_emotion(
        self,
        emotion: str,
        intensity: float = 1.0,
        *,
        transition_duration: float | None = None,
        hold_duration: float | None | object = _HOLD_UNSPECIFIED,
    ) -> None:
        """触发一次情绪表情解算(过渡→保持→自动回中性)。需已连接并加载模型。

        emotion 须为 available_emotions 中的值;非法值抛 ValueError。表情控制器未就绪
        (未连接/未加载模型)时抛 RuntimeError。intensity 为表情强度 [0,1],缺省 1.0,
        0 时所有被控参数回归 neutral(仅缩放 AU 参数,不影响原生表情)。
        transition_duration 为过渡时长(秒,>=0),None 用模型配置。
        hold_duration: 未传=配置默认; float=保持秒数; 显式 None=无限保持直到 cancel
        (供表演时间线 end 约束释放)。
        """

        try:
            kind = EmotionKind(emotion)
        except ValueError as exc:
            raise ValueError(f"未知情绪: {emotion}") from exc
        runtime = self.animation_manager.get_runtime(self.platform.name)
        if EXPRESSION_CONTROLLER not in runtime.controllers:
            raise RuntimeError("表情控制器未就绪(请先连接并加载模型)")
        kwargs: dict[str, object] = {
            "emotion": kind.value,
            "intensity": intensity,
            "transition_duration": transition_duration,
        }
        if hold_duration is not _HOLD_UNSPECIFIED:
            kwargs["hold_duration"] = hold_duration  # may be None = infinite
        await runtime.execute_controller(EXPRESSION_CONTROLLER, **kwargs)

    async def speak(self, text: str, *, subtitle: str | None = None) -> None:
        """触发一次 TTS 发声,经 TTSpeak 控制器(配置驱动音色/连接校验/切源/合成/字幕)。

        文本校验在此抛错供 MCP 即时反馈;切源、调 tts_source、字幕推送全部收敛到
        ``TTSpeakController.execute``。需已连接并加载模型(控制器就绪)。

        Args:
            text: 合成文本(非空)。
            subtitle: 字幕全文; ``None`` 表示与 text 相同; 空串表示不推字幕。
        """

        if not isinstance(text, str):
            raise TypeError("speak 文本须为 str")
        if not text.strip():
            raise ValueError("speak 文本不能为空")
        if subtitle is not None and not isinstance(subtitle, str):
            raise TypeError("subtitle 须为 str 或 None")
        runtime = self.animation_manager.get_runtime(self.platform.name)
        if TTS_SPEAK_CONTROLLER not in runtime.controllers:
            raise RuntimeError("TTSpeak 控制器未就绪(请先连接并加载模型)")
        payload: dict[str, object] = {"text": text.strip()}
        if subtitle is not None:
            payload["subtitle"] = subtitle
        await runtime.execute_controller(TTS_SPEAK_CONTROLLER, **payload)

    async def stop_speaking(self) -> None:
        """停止进行中的 TTS 发声(幂等),经 TTSpeak 控制器。"""

        runtime = self.animation_manager.get_runtime(self.platform.name)
        if TTS_SPEAK_CONTROLLER in runtime.controllers:
            await runtime.stop_controller(TTS_SPEAK_CONTROLLER)

    # --- 表演时间线(供 MCP:唯一表演入口为草稿+入队) ---

    def performance_add_event(
        self,
        event_type: str,
        params: dict[str, object] | None = None,
        *,
        event_id: str | None = None,
        start_anchor: str = "group",
        start_phase: str = "start",
        delay: float = 0.0,
        end_anchor: str | None = None,
        end_phase: str = "end",
        end_delay: float = 0.0,
    ) -> dict[str, object]:
        """向当前事件组添加事件;可选 end_* 为通用强制结束约束。"""

        snap = self.performance.add_event(
            event_type,
            params,
            event_id=event_id,
            start_anchor=start_anchor,
            start_phase=start_phase,
            delay=delay,
            end_anchor=end_anchor,
            end_phase=end_phase,
            end_delay=end_delay,
        )
        return snap.model_dump(mode="json")

    def performance_remove_event(self, event_id: str) -> dict[str, object]:
        """从当前事件组删除事件。"""

        return self.performance.remove_event(event_id).model_dump(mode="json")

    def performance_get_draft(self) -> dict[str, object]:
        """查看当前事件组。"""

        return self.performance.get_draft().model_dump(mode="json")

    def performance_clear_draft(self) -> dict[str, object]:
        """清空当前事件组。"""

        return self.performance.clear_draft().model_dump(mode="json")

    async def performance_enqueue_draft(self, delay: float = 0.0) -> dict[str, object]:
        """把当前事件组快照入队;delay 为轮到执行后再推迟开演的秒数。"""

        result = await self.performance.enqueue_draft(delay=delay)
        return result.model_dump(mode="json")

    def performance_list_jobs(
        self,
        *,
        include_finished: bool = False,
        limit: int = 20,
    ) -> dict[str, object]:
        """列出队列(running/pending/可选 finished)。"""

        return self.performance.list_jobs(
            include_finished=include_finished,
            limit=limit,
        ).model_dump(mode="json")

    def performance_get_job(self, job_id: str) -> dict[str, object] | None:
        """获取指定 job 详情;不存在返回 None。"""

        snap = self.performance.get_job(job_id)
        return None if snap is None else snap.model_dump(mode="json")

    async def performance_remove_job(
        self,
        job_id: str | None = None,
        *,
        clear_all: bool = False,
    ) -> dict[str, object]:
        """删除 pending job 或取消 running;clear_all=True 清空队列。"""

        result = await self.performance.remove_job(job_id, clear_all=clear_all)
        return result.model_dump(mode="json")

    def performance_summary(self) -> str:
        """一行摘要,供 MCP runtime_context 注入。"""

        return self.performance.summary_line()

    async def load_current_model(self) -> None:
        """订阅模型事件并加载当前模型配置"""

        await self._subscribe_model_events()
        await self._load_active_model_config()

    async def _refresh_for_model(self, model_id: str, model_name: str) -> None:
        """重建模型配置并同步平台原生态与动画控制器，完成后广播模型变更。

        编排次序固定:重载配置 → 同步原生态 → 应用到动画运行流程 → 广播。子类通过
        覆盖各钩子定制每一步的平台具体行为,但不改变调用次序。
        """

        model_config = await self._reload_model_config(model_id, model_name)
        await self._sync_native_state(model_config)
        await self._apply_model_config(model_config)
        await self._notify_model_changed(model_id, model_name)

    async def _notify_model_changed(self, model_id: str, model_name: str) -> None:
        """广播模型变更：同步或异步监听器都支持，异常隔离不影响主流程。"""

        listener = self._model_changed_listener
        if listener is None:
            return
        try:
            result = listener(model_id, model_name)
            if isinstance(result, Awaitable):
                await result
        except Exception:
            logger.exception("模型变更监听器执行失败，已隔离")

    async def _notify_state(self, event: PlatformStateEvent) -> None:
        """广播平台运行态变更:同步或异步监听器都支持,异常隔离不影响主流程。"""

        listener = self._state_changed_listener
        if listener is None:
            return
        try:
            result = listener(event)
            if isinstance(result, Awaitable):
                await result
        except Exception:
            logger.exception("平台运行态监听器执行失败,已隔离")

    # --- 平台特有钩子(子类实现/覆盖) ---

    @abstractmethod
    async def _subscribe_model_events(self) -> None:
        """订阅本平台的模型加载/切换事件(幂等:已订阅则跳过)"""

    @abstractmethod
    async def _load_active_model_config(self) -> None:
        """读取当前已加载模型并触发一次 _refresh_for_model"""

    @abstractmethod
    async def _reload_model_config(self, model_id: str, model_name: str) -> TModelConfig:
        """按模型身份重建并返回模型级配置"""

    @abstractmethod
    async def _apply_model_config(self, config: TModelConfig) -> None:
        """把模型配置应用到动画运行流程(构建/复用控制器并重载)"""

    async def _sync_native_state(self, config: TModelConfig) -> None:
        """同步平台原生态(如 VTS exp3 表情开关);默认空操作,支持的平台覆盖。"""

        _ = config

    def _on_disconnected(self) -> None:
        """断开/停止后复位平台特有内部态(如事件订阅句柄);默认空操作。"""
