"""模型表情配置同步子服务。"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from pydantic import BaseModel

from livestudio.config import ConfigManager
from livestudio.log import logger

from .....clients.vtube_studio.models import (
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
    ExpressionStateRequest,
    ExpressionStateRequestData,
    ModelLoadedEvent,
)
from ..base import VTubeStudioSubservice
from .models import (
    ManagedExpressionConfig,
    ManagedModelExpressionConfig,
    ModelExpressionSyncConfigFile,
)


class ModelExpressionSyncService(VTubeStudioSubservice[ModelExpressionSyncConfigFile]):
    """订阅模型切换事件，并按模型配置同步表情状态。"""

    def __init__(self) -> None:
        super().__init__(
            "model_expression_sync",
            ModelExpressionSyncConfigFile,
            Path("config") / "model_expression_sync.yaml",
        )
        self._sync_lock = asyncio.Lock()
        self._sync_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        if not self.enabled:
            logger.info("模型表情同步逻辑已禁用，跳过启动")
            return

        await self.vtubestudio.subscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded_event,
        )
        logger.info("模型表情同步子服务已启动")

        if self.config.config.sync_on_startup:
            await self.sync_current_model()

    async def stop(self) -> None:
        await self.vtubestudio.unsubscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded_event,
        )
        if self._sync_task is not None:
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
        self._sync_task = None
        logger.info("模型表情同步子服务已停止")

    async def close(self) -> None:
        await self.stop()

    async def sync_current_model(self) -> None:
        async with self._sync_lock:
            current_model_response = await self.vtubestudio.client.get_current_model()
            current_model = current_model_response.data
            if not current_model.model_loaded:
                logger.info("当前未加载模型，跳过表情同步")
                return

            expression_response = await self.vtubestudio.client.get_expression_state(
                ExpressionStateRequest(data=ExpressionStateRequestData(details=True)),
            )
            expression_states = expression_response.data.expressions
            model_config_path = (
                Path(
                    "config/models",
                )
                / f"{current_model.model_name}_{current_model.model_id}.yaml"
            )
            model_config_manager = ConfigManager(
                ManagedModelExpressionConfig,
                model_config_path,
            )
            expression = [
                ManagedExpressionConfig(
                    name=state.name,
                    file=state.file,
                    active=state.active,
                )
                for state in expression_states
            ]
            if not model_config_manager.path.exists():
                model_config_manager.config.model_name = current_model.model_name
                model_config_manager.config.model_id = current_model.model_id
                model_config_manager.config.expressions = expression
                await model_config_manager.save()
                logger.info(
                    "未找到模型表情配置，已按当前状态创建: {}",
                    model_config_path,
                )
                return

            await model_config_manager.load()
            config_updated = False

            if model_config_manager.config.model_name != current_model.model_name:
                model_config_manager.config.model_name = current_model.model_name
                config_updated = True
            if model_config_manager.config.model_id != current_model.model_id:
                model_config_manager.config.model_id = current_model.model_id
                config_updated = True

            configured_expressions = {
                item.file: item for item in model_config_manager.config.expressions
            }
            for state in expression_states:
                target_expression = configured_expressions.get(state.file)
                if target_expression is None:
                    target_expression = ManagedExpressionConfig(
                        name=state.name,
                        file=state.file,
                        active=False,
                    )
                    model_config_manager.config.expressions.append(target_expression)
                    configured_expressions[state.file] = target_expression
                    config_updated = True
                elif target_expression.name != state.name:
                    target_expression.name = state.name
                    config_updated = True

                if state.active == target_expression.active:
                    continue

                await self.vtubestudio.client.set_expression_active(
                    ExpressionActivationRequest(
                        data=ExpressionActivationRequestData(
                            expressionFile=target_expression.file,
                            active=target_expression.active,
                            fadeTime=self.config.config.activation_fade_time,
                        ),
                    ),
                )

            if config_updated:
                await model_config_manager.save()

    async def _handle_model_loaded_event(self, event: object) -> None:
        payload = (
            event.model_dump(by_alias=True) if isinstance(event, BaseModel) else event
        )
        model_loaded_event = ModelLoadedEvent.model_validate(payload)
        if not model_loaded_event.data.model_loaded:
            logger.info("收到模型卸载事件，跳过表情同步")
            return

        logger.info(
            "收到模型加载事件，准备同步表情配置: {} ({})",
            model_loaded_event.data.model_name,
            model_loaded_event.data.model_id,
        )
        existing_task = self._sync_task
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()

        self._sync_task = asyncio.create_task(self._sync_current_model_after_event())

    async def _sync_current_model_after_event(self) -> None:
        try:
            await self.sync_current_model()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("模型加载后同步表情配置失败")
