"""配置相关异常层级定义。"""

from __future__ import annotations


class ConfigError(Exception):
    """配置管理的基础异常。"""


class ConfigFormatError(ConfigError):
    """当配置文件格式不受支持或格式错误时抛出。"""


class ConfigLoadError(ConfigError):
    """当配置文件无法加载时抛出。"""


class ConfigSaveError(ConfigError):
    """当配置文件无法持久化保存时抛出。"""


class ConfigValidationError(ConfigError):
    """当配置数据未通过模式校验时抛出。"""
