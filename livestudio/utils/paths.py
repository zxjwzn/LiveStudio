"""这里统一管理 LiveStudio 要用到的文件路径"""

import os
from pathlib import Path

UTILS_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = UTILS_ROOT.parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def _default_home_dir() -> Path:
    override = os.environ.get("LIVESTUDIO_HOME")
    if override:
        return Path(override).expanduser()

    return PROJECT_ROOT


def _default_resource_dir() -> Path:
    override = os.environ.get("LIVESTUDIO_RESOURCE_DIR")
    if override:
        return Path(override).expanduser()

    project_resources = PROJECT_ROOT / "resources"
    if project_resources.exists():
        return project_resources

    return PACKAGE_ROOT / "resources"


HOME_DIR = _default_home_dir()
CONFIG_DIR = HOME_DIR / "configs"
RESOURCE_DIR = _default_resource_dir()


def config_path(*parts: str | os.PathLike[str]) -> Path:
    """返回配置文件夹下面的路径"""

    return CONFIG_DIR.joinpath(*parts)


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    """返回资源文件夹下面的路径"""

    return RESOURCE_DIR.joinpath(*parts)


def resolve_config_path(path: str | os.PathLike[str]) -> Path:
    """把配置路径整理成稳定可用的路径

    绝对路径为有意设计，原样返回；相对路径解析后必须落在 CONFIG_DIR 内，
    拒绝 ``..`` 穿越逃出配置目录（防越权读写）。
    """

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate

    resolved = CONFIG_DIR.joinpath(*candidate.parts[1:]) if candidate.parts[:1] == ("configs",) else CONFIG_DIR / candidate

    base = CONFIG_DIR.resolve()
    if not resolved.resolve().is_relative_to(base):
        raise ValueError(f"配置路径越界，拒绝访问 configs 之外: {path}")
    return resolved
