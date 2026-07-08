"""GUI 桥接常量"""

from typing import Final

from qfluentwidgets import FluentIcon

from livestudio.gui.core import colors
from livestudio.services.expression.models import EmotionKind

from .platform_bridge import ConnectionState, ControllerSpec, EmotionSpec

VTUBESTUDIO_CONTROLLER_SPECS: Final[tuple[ControllerSpec, ...]] = (
    ControllerSpec("blink", "眨眼", FluentIcon.VIEW),
    ControllerSpec("breathing", "呼吸", FluentIcon.HEART),
    ControllerSpec("gaze", "眼神注视", FluentIcon.VIEW),
    ControllerSpec("mouth_expression", "嘴部表情", FluentIcon.EMOJI_TAB_SYMBOLS),
    ControllerSpec("mouth_sync", "口型同步", FluentIcon.MICROPHONE),
)

VTUBESTUDIO_EMOTION_SPECS: Final[tuple[EmotionSpec, ...]] = (
    EmotionSpec(EmotionKind.JOY.value, "喜悦", "😊"),
    EmotionSpec(EmotionKind.ANGER.value, "愤怒", "😠"),
    EmotionSpec(EmotionKind.SADNESS.value, "悲伤", "😢"),
    EmotionSpec(EmotionKind.SURPRISE.value, "惊讶", "😲"),
    EmotionSpec(EmotionKind.SMUG.value, "阴险", "😏"),
    EmotionSpec(EmotionKind.WRY.value, "无奈", "😅"),
    EmotionSpec(EmotionKind.SHY.value, "害羞", "😳"),
)

CONNECTION_STATE_COLOR: Final[dict[ConnectionState, str]] = {
    ConnectionState.DISCONNECTED: colors.NEUTRAL,
    ConnectionState.CONNECTING: colors.WARNING,
    ConnectionState.CONNECTED: colors.SUCCESS,
    ConnectionState.ERROR: colors.ERROR,
}

CONNECTION_STATE_TEXT: Final[dict[ConnectionState, str]] = {
    ConnectionState.DISCONNECTED: "未连接",
    ConnectionState.CONNECTING: "连接中…",
    ConnectionState.CONNECTED: "已连接",
    ConnectionState.ERROR: "连接错误",
}
