"""Centralized filesystem paths for LiveStudio."""

from __future__ import annotations

import os
import sys
from pathlib import Path

UTILS_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = UTILS_ROOT.parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def _default_home_dir() -> Path:
    override = os.environ.get("LIVESTUDIO_HOME")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "LiveStudio"

    return Path.home() / ".config" / "livestudio"


def _default_resource_dir() -> Path:
    override = os.environ.get("LIVESTUDIO_RESOURCE_DIR")
    if override:
        return Path(override).expanduser()

    project_resources = PROJECT_ROOT / "resources"
    if project_resources.exists():
        return project_resources

    return PACKAGE_ROOT / "resources"


HOME_DIR = _default_home_dir()
CONFIG_DIR = HOME_DIR / "config"
RESOURCE_DIR = _default_resource_dir()


def config_path(*parts: str | os.PathLike[str]) -> Path:
    """Return a path under the user-writable config directory."""

    return CONFIG_DIR.joinpath(*parts)


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    """Return a path under the configured resource directory."""

    return RESOURCE_DIR.joinpath(*parts)


def resolve_config_path(path: str | os.PathLike[str]) -> Path:
    """Resolve user config paths without depending on the process cwd."""

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate

    if candidate.parts[:1] == ("config",):
        return HOME_DIR / candidate

    return CONFIG_DIR / candidate
