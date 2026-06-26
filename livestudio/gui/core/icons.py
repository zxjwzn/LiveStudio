"""集中的 FluentIcon 映射

全 GUI 只从这里取图标,统一为 QFluentWidgets 矢量图标(不用 emoji)。导航、
日志级别等图标在此一处定义,避免散落各页导致风格漂移。
"""

from qfluentwidgets import FluentIcon

# 导航项图标(仪表盘 / 平台 / 音频 / 日志 / 设置)
NAV_DASHBOARD = FluentIcon.HOME
NAV_PLATFORM = FluentIcon.ROBOT
NAV_AUDIO = FluentIcon.MUSIC
NAV_LOGS = FluentIcon.HISTORY
NAV_SETTINGS = FluentIcon.SETTING

# 日志级别图标
LOG_DEBUG = FluentIcon.DEVELOPER_TOOLS
LOG_INFO = FluentIcon.INFO
LOG_WARNING = FluentIcon.RINGER
LOG_ERROR = FluentIcon.MEGAPHONE

# 连接/控制相关
ACTION_CONNECT = FluentIcon.CONNECT
ACTION_LAN_SEARCH = FluentIcon.LINK
ACTION_PLAY = FluentIcon.PLAY
ACTION_PAUSE = FluentIcon.PAUSE
ACTION_EXPRESSION = FluentIcon.EMOJI_TAB_SYMBOLS
