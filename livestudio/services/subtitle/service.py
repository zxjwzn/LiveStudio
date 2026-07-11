"""字幕 WebSocket 服务

订阅 ``SubtitleStream`` 总线,把 begin/segments/finish 映射为新协议 JSON 并广播给
浏览器(OBS 源)。独立 uvicorn + Starlette,生命周期与 MCP 同构:传输跑在专用任务,
避免 anyio cancel scope 跨任务退出。

协议(服务端 → 浏览器,无旧协议兼容):
  {"type":"begin","data":{text, font_*, audio_delay_ms, clear_delay_ms}}
  {"type":"segments","data":{"segments":[{"text","start","end"}, ...]}}
  {"type":"finish"}
  {"type":"pong"}  # 应答客户端 {"type":"ping"}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from livestudio.config import ConfigManager
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.utils.log import logger
from livestudio.utils.paths import PROJECT_ROOT, config_path

from .config import SubtitleConfig
from .stream import SubtitleEvent, SubtitleStream, SubtitleSubscription

_GRACEFUL_SHUTDOWN_TIMEOUT = 1
_HTML_CANDIDATES = (
    PROJECT_ROOT / "docs" / "index.html",
    Path(__file__).resolve().parent / "static" / "index.html",
)


class SubtitleService(AsyncServiceLifecycleMixin):
    """订阅字幕总线并通过 WebSocket 推送到网页"""

    def __init__(
        self,
        stream: SubtitleStream,
        *,
        config_manager: ConfigManager[SubtitleConfig] | None = None,
    ) -> None:
        self._stream = stream
        self._config_manager = config_manager or ConfigManager(
            SubtitleConfig,
            config_path("subtitle.yaml"),
        )
        self._subscription: SubtitleSubscription | None = None
        self._relay_task: asyncio.Task[None] | None = None
        self._transport_task: asyncio.Task[None] | None = None
        self._uvicorn: uvicorn.Server | None = None
        self._clients: set[WebSocket] = set()
        self._clients_lock = asyncio.Lock()

    @property
    def config(self) -> SubtitleConfig:
        return self._config_manager.config

    @property
    def endpoint_url(self) -> str:
        """浏览器源应打开的 HTTP 地址"""

        cfg = self.config
        host = cfg.host if cfg.host not in ("0.0.0.0", "::") else "127.0.0.1"
        return f"http://{host}:{cfg.port}/"

    @property
    def ws_url(self) -> str:
        cfg = self.config
        host = cfg.host if cfg.host not in ("0.0.0.0", "::") else "127.0.0.1"
        return f"ws://{host}:{cfg.port}/ws/subtitles"

    async def apply_config(self, config: SubtitleConfig) -> None:
        """校验落盘;运行中则按 enabled/host/port 重启或停止传输"""

        await self._config_manager.save(config)
        if not self.is_started:
            return
        if not config.enabled:
            await self._stop_transport()
            await self._stop_relay()
            logger.info("字幕服务已按配置停用传输")
            return
        # 已启用:确保中继与传输在跑(可能从 disabled 切来,或改 host/port)
        if self._relay_task is None or self._relay_task.done():
            await self._start_relay()
        await self._restart_transport()
        logger.info("字幕服务已按新配置重启: {}", self.endpoint_url)

    async def _do_start(self) -> None:
        await self._config_manager.load()
        if not self.config.enabled:
            logger.info("字幕服务已加载但未启用(enabled=false)")
            return
        await self._start_relay()
        await self._start_transport()

    async def _do_stop(self) -> None:
        await self._stop_transport()
        await self._stop_relay()
        with contextlib.suppress(Exception):
            await self._config_manager.save()
        logger.info("字幕服务已停止")

    async def _do_restart(self) -> None:
        await self._do_stop()
        await self._do_start()

    async def _start_relay(self) -> None:
        if self._relay_task is not None and not self._relay_task.done():
            return
        self._subscription = self._stream.subscribe(queue_maxsize=128)
        self._relay_task = asyncio.create_task(self._relay_loop())

    async def _stop_relay(self) -> None:
        task = self._relay_task
        self._relay_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._subscription is not None:
            self._stream.unsubscribe(self._subscription)
            self._subscription = None

    async def _relay_loop(self) -> None:
        sub = self._subscription
        if sub is None:
            return
        try:
            while True:
                event = await sub.queue.get()
                message = self._event_to_message(event)
                if message is not None:
                    await self._broadcast(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("字幕中继任务异常")

    def _event_to_message(self, event: SubtitleEvent) -> dict[str, object] | None:
        cfg = self.config
        if event.kind == "begin":
            return {
                "type": "begin",
                "data": {
                    "text": event.text or "",
                    "font_path": cfg.font_path,
                    "font_size": cfg.font_size,
                    "font_color": cfg.font_color,
                    "font_edge_color": cfg.font_edge_color,
                    "font_edge_width": cfg.font_edge_width,
                    "audio_delay_ms": cfg.audio_delay_ms,
                    "clear_delay_ms": cfg.clear_delay_ms,
                },
            }
        if event.kind == "segments":
            segs = event.segments or []
            return {
                "type": "segments",
                "data": {
                    "segments": [{"text": s.text, "start": s.start, "end": s.end} for s in segs],
                },
            }
        if event.kind == "finish":
            return {"type": "finish"}
        return None

    async def _broadcast(self, message: dict[str, object]) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        async with self._clients_lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._clients_lock:
                for ws in dead:
                    self._clients.discard(ws)

    def _build_app(self) -> Starlette:
        service = self

        async def index(_request: Request) -> Response:
            for path in _HTML_CANDIDATES:
                if path.is_file():
                    return FileResponse(path, media_type="text/html; charset=utf-8")
            return HTMLResponse("<h1>subtitle page missing</h1>", status_code=404)

        async def font_file(request: Request) -> Response:
            raw = request.query_params.get("path", "")
            if not raw:
                return PlainTextResponse("missing path", status_code=400)
            path = Path(raw).expanduser()
            if not path.is_file():
                return PlainTextResponse("not found", status_code=404)
            suffix = path.suffix.lower()
            media = {
                ".ttf": "font/ttf",
                ".otf": "font/otf",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
            }.get(suffix, "application/octet-stream")
            return FileResponse(path, media_type=media)

        async def websocket_endpoint(websocket: WebSocket) -> None:
            await websocket.accept()
            async with service._clients_lock:
                service._clients.add(websocket)
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
            except WebSocketDisconnect:
                pass
            except Exception:
                logger.exception("字幕 WebSocket 异常")
            finally:
                async with service._clients_lock:
                    service._clients.discard(websocket)

        return Starlette(
            routes=[
                Route("/", endpoint=index),
                Route("/fonts", endpoint=font_file),
                WebSocketRoute("/ws/subtitles", endpoint=websocket_endpoint),
            ],
        )

    async def _start_transport(self) -> None:
        cfg = self.config
        config = uvicorn.Config(
            self._build_app(),
            host=cfg.host,
            port=cfg.port,
            log_level="warning",
            lifespan="off",
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
            ws="websockets",
        )
        server = uvicorn.Server(config)
        self._uvicorn = server
        self._transport_task = asyncio.create_task(self._run_transport(server))
        while not server.started:
            if self._transport_task.done():
                await self._transport_task
                return
            await asyncio.sleep(0.02)
        logger.success("字幕服务已启动: {} (ws {})", self.endpoint_url, self.ws_url)

    @staticmethod
    async def _run_transport(server: uvicorn.Server) -> None:
        await server.serve()

    async def _restart_transport(self) -> None:
        await self._stop_transport()
        await self._start_transport()

    async def _stop_transport(self) -> None:
        task = self._transport_task
        server = self._uvicorn
        self._transport_task = None
        self._uvicorn = None
        if server is not None:
            server.should_exit = True
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        async with self._clients_lock:
            self._clients.clear()
