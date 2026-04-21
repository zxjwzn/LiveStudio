"""按模型配置自动同步 VTube Studio 表情状态。"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from livestudio.config import ConfigLoadError, ConfigManager, ConfigValidationError
from livestudio.log import logger

from ....clients.vtube_studio.models import (
    EventSubscriptionConfig,
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
    ExpressionState,
    ExpressionStateRequest,
    ExpressionStateRequestData,
    VTSEventEnvelope,
)
from ....clients.vtube_studio.models.model import CurrentModelResponseData
from .models import ModelExpressionConfig, ModelExpressionEntry

if TYPE_CHECKING:
    from ..service import VTubeStudio

_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\s]+')
_MAX_FILENAME_STEM_LENGTH = 80

class ModelExpressionSyncService:
    """VTube Studio 的模型表情同步子服务。"""

    def __init__(
        self,
        service: VTubeStudio,
        *,
        config_root: str | Path = Path("config") / "models",
    ) -> None:
        self._service = service
        self._config_root = Path(config_root)
        self._sync_lock = asyncio.Lock()
        self._started = False
        self._pending_sync_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动模型监听，并立即同步当前模型。"""

        if self._started:
            return

        await self._service.subscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded_event,
            config=EventSubscriptionConfig(),
        )
        self._started = True
        await self.sync_current_model()

    async def close(self) -> None:
        """停止模型监听。"""

        if not self._started:
            return

        try:
            await self._service.unsubscribe("ModelLoadedEvent", self._handle_model_loaded_event)
        finally:
            self._started = False
            pending_sync_task = self._pending_sync_task
            self._pending_sync_task = None
            if pending_sync_task is not None:
                pending_sync_task.cancel()
                await asyncio.gather(pending_sync_task, return_exceptions=True)

    async def sync_current_model(self) -> None:
        """读取当前模型并按配置同步表情状态。"""

        async with self._sync_lock:
            current_model_data, expressions, config_manager = await self._load_current_model_context()
            if current_model_data is None:
                return
            current_model_data, config_manager = self._require_model_context(current_model_data, config_manager)

            config = await self._load_or_create_config(
                config_manager=config_manager,
                model_id=current_model_data.model_id,
                model_name=current_model_data.model_name,
                expressions=expressions,
            )
            await self._apply_expression_config(
                config=config,
                current_expressions=expressions,
                model_name=current_model_data.model_name,
            )

    async def save_current_model_expression_state(self) -> ModelExpressionConfig | None:
        """读取当前模型表情激活状态并保存到配置文件。"""

        async with self._sync_lock:
            current_model_data, expressions, config_manager = await self._load_current_model_context()
            if current_model_data is None:
                return None
            current_model_data, config_manager = self._require_model_context(current_model_data, config_manager)

            config = self._build_model_config(
                model_id=current_model_data.model_id,
                model_name=current_model_data.model_name,
                expressions=expressions,
            )
            return await self._save_config_if_changed(
                config_manager=config_manager,
                config=config,
                created_message="已保存当前模型表情配置: {}",
                updated_message="已更新当前模型表情配置: {}",
            )

    def _handle_model_loaded_event(self, _event: VTSEventEnvelope) -> None:
        """处理模型切换事件。"""

        pending_sync_task = self._pending_sync_task
        if pending_sync_task is not None:
            pending_sync_task.cancel()
        self._pending_sync_task = asyncio.create_task(self._sync_current_model_for_event())

    async def _sync_current_model_for_event(self) -> None:
        """在后台处理模型切换后的表情同步。"""

        try:
            await self.sync_current_model()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("处理模型切换事件失败")

    async def _load_or_create_config(
        self,
        *,
        config_manager: ConfigManager[ModelExpressionConfig],
        model_id: str,
        model_name: str,
        expressions: list[ExpressionState],
    ) -> ModelExpressionConfig:
        existing_config = await self._load_existing_config(config_manager)

        reconciled_config = self._build_reconciled_config(
            existing_config=existing_config,
            model_id=model_id,
            model_name=model_name,
            expressions=expressions,
        )

        return await self._save_config_if_changed(
            config_manager=config_manager,
            config=reconciled_config,
            existing_config=existing_config,
            created_message="已生成模型表情配置: {}",
            updated_message="已刷新模型表情配置: {}",
        )

    async def _load_current_model_context(
        self,
    ) -> tuple[CurrentModelResponseData | None, list[ExpressionState], ConfigManager[ModelExpressionConfig] | None]:
        current_model = await self._service.client.get_current_model()
        current_model_data = current_model.data
        if not current_model_data.model_loaded:
            return None, [], None

        expression_response = await self._service.client.get_expression_state(
            ExpressionStateRequest(data=ExpressionStateRequestData(details=False)),
        )
        config_path = self._get_model_config_path(current_model_data.model_id, current_model_data.model_name)
        return (
            current_model_data,
            expression_response.data.expressions,
            ConfigManager(ModelExpressionConfig, config_path),
        )

    def _require_model_context(
        self,
        current_model_data: CurrentModelResponseData | None,
        config_manager: ConfigManager[ModelExpressionConfig] | None,
    ) -> tuple[CurrentModelResponseData, ConfigManager[ModelExpressionConfig]]:
        if current_model_data is None or config_manager is None:
            raise RuntimeError("当前未加载模型，无法处理模型表情配置")
        return current_model_data, config_manager

    async def _load_existing_config(
        self,
        config_manager: ConfigManager[ModelExpressionConfig],
    ) -> ModelExpressionConfig | None:
        config_path = config_manager.path
        if not config_path.exists():
            return None

        try:
            return await config_manager.load()
        except (ConfigLoadError, ConfigValidationError):
            logger.exception(f"读取模型表情配置失败: {config_path}")
            raise

    async def _save_config_if_changed(
        self,
        *,
        config_manager: ConfigManager[ModelExpressionConfig],
        config: ModelExpressionConfig,
        created_message: str,
        updated_message: str,
        existing_config: ModelExpressionConfig | None = None,
    ) -> ModelExpressionConfig:
        if existing_config is None:
            existing_config = await self._load_existing_config(config_manager)

        if existing_config is not None and not self._is_config_changed(existing_config, config):
            return existing_config

        config_manager.update(
            model_id=config.model_id,
            model_name=config.model_name,
            expressions=config.expressions,
        )
        await config_manager.save()

        logger.info(
            created_message if existing_config is None else updated_message,
            config_manager.path,
        )
        return config_manager.config

    def _build_model_config(
        self,
        *,
        model_id: str,
        model_name: str,
        expressions: list[ExpressionState],
    ) -> ModelExpressionConfig:
        return ModelExpressionConfig(
            model_id=model_id,
            model_name=model_name,
            expressions=[
                ModelExpressionEntry(
                    name=expression.name,
                    file=expression.file,
                    active=expression.active,
                )
                for expression in expressions
            ],
        )

    def _is_config_changed(
        self,
        existing_config: ModelExpressionConfig,
        new_config: ModelExpressionConfig,
    ) -> bool:
        return existing_config.model_dump(mode="json") != new_config.model_dump(mode="json")

    def _build_reconciled_config(
        self,
        *,
        existing_config: ModelExpressionConfig | None,
        model_id: str,
        model_name: str,
        expressions: list[ExpressionState],
    ) -> ModelExpressionConfig:
        existing_entries_by_file = {
            entry.file: entry
            for entry in (existing_config.expressions if existing_config is not None else [])
        }
        reconciled_entries = [
            ModelExpressionEntry(
                name=expression.name,
                file=expression.file,
                active=existing_entry.active if (existing_entry := existing_entries_by_file.get(expression.file)) else expression.active,
            )
            for expression in expressions
        ]
        return ModelExpressionConfig(
            model_id=model_id,
            model_name=model_name,
            expressions=reconciled_entries,
        )

    async def _apply_expression_config(
        self,
        *,
        config: ModelExpressionConfig,
        current_expressions: list[ExpressionState],
        model_name: str,
    ) -> None:
        configured_state_by_file = {entry.file: entry.active for entry in config.expressions}
        changed_count = 0

        for expression in current_expressions:
            desired_active = configured_state_by_file.get(expression.file)
            if desired_active is None or desired_active == expression.active:
                continue

            await self._service.client.set_expression_active(
                ExpressionActivationRequest(
                    data=ExpressionActivationRequestData(
                        expressionFile=expression.file,
                        active=desired_active,
                    ),
                ),
            )
            changed_count += 1
            logger.info(
                "模型 `{}` 表情 `{}` 已{}",
                model_name,
                expression.name,
                "激活" if desired_active else "关闭",
            )

        logger.info(
            "模型 `{}` 表情同步完成，配置项: {}，实际变更: {}",
            model_name,
            len(config.expressions),
            changed_count,
        )

    def _get_model_config_path(self, model_id: str, model_name: str) -> Path:
        file_stem = self._sanitize_file_stem(model_name)
        return self._config_root / f"{file_stem}__{model_id}.yaml"

    def _sanitize_file_stem(self, value: str) -> str:
        sanitized = _INVALID_FILE_CHARS.sub("_", value).strip("._")
        if not sanitized:
            sanitized = "model"
        return sanitized[:_MAX_FILENAME_STEM_LENGTH]