"""GUI 配置读写

复用项目统一的 ConfigManager 契约(文件即全部、保存即快照),把 GuiSettings
持久化到 configs/gui.yaml。这是 GUI 本地偏好,与业务配置同级但互不干扰。
"""

from livestudio.config import ConfigManager
from livestudio.utils.paths import config_path

from .settings_config import GuiSettings

_GUI_SETTINGS_FILENAME = "gui.yaml"


def create_gui_settings_manager() -> ConfigManager[GuiSettings]:
    """构造 GUI 配置管理器(configs/gui.yaml)"""

    return ConfigManager(GuiSettings, config_path(_GUI_SETTINGS_FILENAME))


def create_gui_settings_manager_with(settings: GuiSettings) -> ConfigManager[GuiSettings]:
    """构造一个以给定 settings 为快照的管理器,用于直接落盘(无需读旧文件)"""

    return ConfigManager(GuiSettings, config_path(_GUI_SETTINGS_FILENAME), default_config=settings)
