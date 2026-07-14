"""平台应用编排基类

把「连接 → 加载模型 → 刷新控制器 → 广播变更」这套各平台都一样的编排骨架收敛到一处,
平台特有步骤(订阅何种事件、如何读当前模型、如何同步平台原生态、构建哪些控制器)留给
子类以钩子方法填充。新增平台只需继承本类实现少量抽象钩子,无需重抄生命周期与刷新流程。

模板方法模式:本类定稳调用次序与异常隔离,子类只关心「这一步在本平台上具体怎么做」。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from livestudio.services.animations import AnimationManager
from livestudio.services.animations.constants import TTS_SPEAK_CONTROLLER
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.platforms import PlatformModelConfig, PlatformService
from livestudio.utils.log import logger

# 模型变更监听器：参数为 (model_id, model_name)。后端只负责广播「模型已就绪/已切换」，
# 不关心由谁消费——GUI 适配器等外部观察者据此自我刷新，从而与本应用解耦。
ModelChangedListener = Callable[[str, str], Awaitable[None] | None]

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

    def set_model_changed_listener(self, listener: ModelChangedListener | None) -> None:
        """注册模型变更监听器（首次加载与运行时换模型都会触发）。

        传 None 解除监听。监听器异常被隔离，不影响模型加载主流程。
        """

        self._model_changed_listener = listener

    async def _do_start(self) -> None:
        """启动平台相关应用（含资源准备）。

        启动失败的回滚交由 Mixin 的 start() 统一调用 stop()（即 _do_stop）。
        """

        await self.platform.start()
        await self.load_current_model()
        await self.animation_manager.start()

    async def _do_stop(self) -> None:
        """停止应用并释放资源"""

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

    async def disconnect(self) -> None:
        """断开平台:先停动画控制器,再停平台(镜像 _do_stop 顺序)。"""

        await self.animation_manager.stop()
        await self.platform.stop()
        self._on_disconnected()

    async def start_controllers(self) -> None:
        """启动动画控制器(待机动画)。需平台已连接。"""

        await self.animation_manager.start()

    async def stop_controllers(self) -> None:
        """停止动画控制器(幂等,未运行时为空操作)。"""

        await self.animation_manager.stop()

    # --- 平台无关语义动作 ---

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

    async def speak(self, text: str, **opts: object) -> None:
        """触发一次 TTS 发声,经 TTSpeak 控制器(配置驱动音色/连接校验/切源/合成)。

        音色合并、连接槽校验、切源、调 tts_source 全部
        收敛到 ``TTSpeakController.execute``,本方法作为 GUI 的平台无关公开入口,
        不再直连 tts_source。需已连接并加载模型(控制器就绪)。

        Args:
            text: 要朗读的文本(非空)。
            **opts: 可选 subtitle 及供应商配置覆盖字段，控制器据此构造 TtsSpeakRequest。
        """

        if not isinstance(text, str):
            raise TypeError("speak 文本须为 str")
        if not text.strip():
            raise ValueError("speak 文本不能为空")
        runtime = self.animation_manager.get_runtime(self.platform.name)
        if TTS_SPEAK_CONTROLLER not in runtime.controllers:
            raise RuntimeError("TTSpeak 控制器未就绪(请先连接并加载模型)")
        await runtime.execute_controller(TTS_SPEAK_CONTROLLER, text=text.strip(), **opts)

    async def stop_speaking(self) -> None:
        """停止进行中的 TTS 发声(幂等),经 TTSpeak 控制器。"""

        runtime = self.animation_manager.get_runtime(self.platform.name)
        if TTS_SPEAK_CONTROLLER in runtime.controllers:
            await runtime.stop_controller(TTS_SPEAK_CONTROLLER)

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
