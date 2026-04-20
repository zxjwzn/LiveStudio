"""应用层级的 VTube Studio 服务组合。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from livestudio.clients.vtube_studio import VTubeStudioClient, VTubeStudioPluginInfo
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.examples import build_config_manager
from livestudio.clients.vtube_studio.models import (
    InjectParameterDataRequest,
    InjectParameterDataRequestData,
    InjectParameterValue,
)
from livestudio.clients.vtube_studio.service import VTubeStudioService
from livestudio.config import ConfigManager
from livestudio.tween import ControlledParameterState, ParameterTweenEngine, TweenMode


class ManagedVTubeStudioService:
    """在客户端库之外组合 VTube Studio API 门面与缓动引擎。"""

    def __init__(
        self,
        api: VTubeStudioService,
        *,
        config_manager: ConfigManager[VTubeStudioConfig] | None = None,
        tween_keep_alive_interval: float = 0.8,
        tween_default_fps: int = 60,
    ) -> None:
        self.api = api
        self.config_manager = config_manager
        self.tween = ParameterTweenEngine(
            self._send_parameter_states,
            keep_alive_interval=tween_keep_alive_interval,
            default_fps=tween_default_fps,
        )

    def __getattr__(self, item: str) -> Any:
        return getattr(self.api, item)

    async def close(self) -> None:
        """关闭应用层持有的资源。"""

        await self.tween.close()
        await self.api.close()

    async def _send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: TweenMode,
    ) -> None:
        parameter_states = list(states)
        if not parameter_states:
            return

        request = InjectParameterDataRequest(
            data=InjectParameterDataRequestData(
                mode=mode,
                parameterValues=[
                    InjectParameterValue(id=state.name, value=state.value)
                    for state in parameter_states
                ],
            ),
        )
        await self.api.inject_parameter_data(request)


async def build_managed_vtube_studio_service(
    config_path: str | Path | None = None,
) -> ManagedVTubeStudioService:
    """构建应用层级的 VTube Studio 服务。"""

    config_manager = build_config_manager(config_path)
    await config_manager.load()
    plugin_info = VTubeStudioPluginInfo(
        plugin_name="LiveStudio",
        plugin_developer="Zaxpris",
    )
    client = VTubeStudioClient(config=config_manager.config, plugin_info=plugin_info)
    api = VTubeStudioService(client, config_manager=config_manager)
    return ManagedVTubeStudioService(api, config_manager=config_manager)