"""模型表情配置同步子服务。"""

from __future__ import annotations

import asyncio
import contextlib
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigStore
from livestudio.log import logger

from ....clients.vtube_studio.models import (
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
    ExpressionState,
    ExpressionStateRequest,
    ExpressionStateRequestData,
    ModelLoadedEvent,
)
from .base import SubserviceConfigFile, VTubeStudioSubservice

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ManagedExpressionConfig(BaseModel):
    """单个表情的持久化配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="表情名称。")
    file: str = Field(min_length=1, description="表情文件名。")
    active: bool = Field(description="是否在模型加载后激活。")


class ManagedModelExpressionConfig(BaseModel):
    """单个模型的表情配置文件。"""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1, description="模型名称。")
    model_id: str = Field(min_length=1, description="模型 ID。")
    expressions: list[ManagedExpressionConfig] = Field(default_factory=list, description="该模型的表情激活配置。")


class ModelExpressionSyncConfig(BaseModel):
    """模型表情同步逻辑配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用模型表情同步逻辑。")
    models_dir: str = Field(default="config/models", description="模型表情配置目录。")
    sync_on_startup: bool = Field(default=True, description="服务启动后是否立即同步当前模型表情。")
    activation_fade_time: float = Field(default=0.25, ge=0, le=2, description="表情切换淡入时长。")

    def resolve_models_dir(self) -> Path:
        return Path(self.models_dir)


class ModelExpressionSyncConfigFile(SubserviceConfigFile[ModelExpressionSyncConfig]):
    """模型表情同步子服务配置文件。"""

    config: ModelExpressionSyncConfig = Field(default_factory=ModelExpressionSyncConfig)


class ModelExpressionSyncService(VTubeStudioSubservice[ModelExpressionSyncConfigFile]):
    """订阅模型切换事件，并按模型配置同步表情状态。"""

    def __init__(self, *, config_path: str | Path | None = None) -> None:
        super().__init__("model_expression_sync", ModelExpressionSyncConfigFile, config_path=config_path)
        self._store = ConfigStore()
        self._sync_lock = asyncio.Lock()
        self._started = False
        self._sync_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        self.config.config.resolve_models_dir().mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        if self._started:
            return
        if not self.config.config.enabled:
            logger.info("模型表情同步逻辑已禁用，跳过启动")
            return

        await self.vtubestudio.subscribe("ModelLoadedEvent", self._handle_model_loaded_event)
        self._started = True
        logger.info("模型表情同步子服务已启动")

        if self.config.config.sync_on_startup:
            await self.sync_current_model()

    async def stop(self) -> None:
        if not self._started:
            return

        await self.vtubestudio.unsubscribe("ModelLoadedEvent", self._handle_model_loaded_event)
        sync_task = self._sync_task
        self._sync_task = None
        if sync_task is not None:
            sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sync_task
        self._started = False
        logger.info("模型表情同步子服务已停止")

    async def close(self) -> None:
        await self.stop()

    async def save_config(self) -> None:
        await self.config_manager.save()

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
            model_config_path = self._build_model_config_path(current_model.model_name, current_model.model_id)
            model_config = self._load_or_build_model_config(
                model_name=current_model.model_name,
                model_id=current_model.model_id,
                expression_states=expression_states,
                path=model_config_path,
            )
            await self._apply_expression_config(expression_states, model_config)

    async def _handle_model_loaded_event(self, event: object) -> None:
        payload = event.model_dump(by_alias=True) if isinstance(event, BaseModel) else event
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

    def _load_or_build_model_config(
        self,
        *,
        model_name: str,
        model_id: str,
        expression_states: list[ExpressionState],
        path: Path,
    ) -> ManagedModelExpressionConfig:
        generated_config = self._build_model_config(
            model_name=model_name,
            model_id=model_id,
            expression_states=expression_states,
        )
        if not path.exists():
            self._save_model_config(path, generated_config)
            logger.info("已为模型生成表情配置文件: {}", path)
            return generated_config

        existing_config = ManagedModelExpressionConfig.model_validate(self._store.load_dict(path))
        merged_config = self._merge_model_config(existing_config, generated_config)
        if merged_config != existing_config:
            self._save_model_config(path, merged_config)
            logger.info("已刷新模型表情配置文件: {}", path)
        return merged_config

    def _build_model_config(
        self,
        *,
        model_name: str,
        model_id: str,
        expression_states: list[ExpressionState],
    ) -> ManagedModelExpressionConfig:
        return ManagedModelExpressionConfig(
            model_name=model_name,
            model_id=model_id,
            expressions=[
                ManagedExpressionConfig(name=expression.name, file=expression.file, active=expression.active)
                for expression in expression_states
            ],
        )

    def _merge_model_config(
        self,
        existing_config: ManagedModelExpressionConfig,
        generated_config: ManagedModelExpressionConfig,
    ) -> ManagedModelExpressionConfig:
        existing_active_by_file = {expression.file: expression.active for expression in existing_config.expressions}
        merged_expressions = [
            ManagedExpressionConfig(
                name=expression.name,
                file=expression.file,
                active=existing_active_by_file.get(expression.file, expression.active),
            )
            for expression in generated_config.expressions
        ]
        return ManagedModelExpressionConfig(
            model_name=generated_config.model_name,
            model_id=generated_config.model_id,
            expressions=merged_expressions,
        )

    async def _apply_expression_config(
        self,
        expression_states: list[ExpressionState],
        model_config: ManagedModelExpressionConfig,
    ) -> None:
        desired_state_by_file = {expression.file: expression.active for expression in model_config.expressions}
        changed_count = 0
        for expression_state in expression_states:
            desired_active = desired_state_by_file.get(expression_state.file)
            if desired_active is None or desired_active == expression_state.active:
                continue

            await self.vtubestudio.client.set_expression_active(
                ExpressionActivationRequest(
                    data=ExpressionActivationRequestData(
                        expressionFile=expression_state.file,
                        fadeTime=self.config.config.activation_fade_time,
                        active=desired_active,
                    ),
                ),
            )
            changed_count += 1

        logger.info("模型表情同步完成，实际变更数量: {}", changed_count)

    def _build_model_config_path(self, model_name: str, model_id: str) -> Path:
        file_name = f"{self._sanitize_filename_part(model_name)}_{self._sanitize_filename_part(model_id)}.yaml"
        return self.config.config.resolve_models_dir() / file_name

    def _sanitize_filename_part(self, value: str) -> str:
        sanitized = _INVALID_FILENAME_CHARS.sub("_", value).strip().strip(".")
        if sanitized:
            return sanitized
        return "unknown"

    def _save_model_config(self, path: Path, model_config: ManagedModelExpressionConfig) -> None:
        self._store.save_dict(path, model_config.model_dump(mode="json", exclude_none=True))