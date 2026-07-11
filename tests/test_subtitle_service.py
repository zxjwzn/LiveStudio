"""字幕服务:事件映射与配置"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio

from livestudio.services.subtitle import (
    SubtitleConfig,
    SubtitleEvent,
    SubtitleSegment,
    SubtitleService,
    SubtitleStream,
)


def test_event_to_message_begin_includes_style() -> None:
    stream = SubtitleStream()
    service = SubtitleService(stream)
    # 不启动服务,直接改内存配置
    service._config_manager._current = SubtitleConfig(
        font_size=60,
        font_color="#FF0000",
        audio_delay_ms=200,
        clear_delay_ms=1500,
        font_path="C:/fonts/a.ttf",
    )
    msg = service._event_to_message(SubtitleEvent(kind="begin", text="你好"))
    assert msg is not None
    assert msg["type"] == "begin"
    data = msg["data"]
    assert isinstance(data, dict)
    assert data["text"] == "你好"
    assert data["font_size"] == 60
    assert data["font_color"] == "#FF0000"
    assert data["audio_delay_ms"] == 200
    assert data["clear_delay_ms"] == 1500
    assert data["font_path"] == "C:/fonts/a.ttf"


def test_event_to_message_segments_and_finish() -> None:
    service = SubtitleService(SubtitleStream())
    segs = [SubtitleSegment(text="a", start=0.0, end=0.2)]
    msg = service._event_to_message(SubtitleEvent(kind="segments", segments=segs))
    assert msg is not None
    assert msg["type"] == "segments"
    data = msg["data"]
    assert isinstance(data, dict)
    assert data["segments"] == [{"text": "a", "start": 0.0, "end": 0.2}]

    fin = service._event_to_message(SubtitleEvent(kind="finish"))
    assert fin == {"type": "finish"}


async def test_relay_broadcasts_to_stream_subscriber_mapping() -> None:
    """总线 begin/segments/finish 经中继映射后可被内部捕获(不启真实 uvicorn)"""

    stream = SubtitleStream()
    service = SubtitleService(stream)
    received: list[dict[str, object]] = []

    async def capture(message: dict[str, object]) -> None:
        received.append(message)

    service._broadcast = capture  # type: ignore[method-assign]
    await service._start_relay()
    try:
        stream.begin("hello")
        stream.publish_segments([SubtitleSegment(text="he", start=0.0, end=0.1)])
        stream.finish()
        await asyncio.sleep(0.05)
    finally:
        await service._stop_relay()

    assert [m["type"] for m in received] == ["begin", "segments", "finish"]
    assert received[0]["data"]["text"] == "hello"  # type: ignore[index]


async def test_apply_config_disabled_stops_transport(tmp_path) -> None:
    from livestudio.config import ConfigManager

    stream = SubtitleStream()
    path = tmp_path / "subtitle.yaml"
    mgr = ConfigManager(SubtitleConfig, path, default_config=SubtitleConfig(enabled=True, port=18765))
    service = SubtitleService(stream, config_manager=mgr)
    await service.start()
    assert service.is_started
    # 端口可能被占用则 start 失败——用高端口降低冲突;若失败 skip
    if service._uvicorn is None and service.config.enabled:
        # transport 未起来(端口问题),仍测 apply 落盘
        pass
    await service.apply_config(SubtitleConfig(enabled=False, port=18765))
    assert service.config.enabled is False
    assert service._uvicorn is None
    await service.stop()


def test_endpoint_url_maps_wildcard_host() -> None:
    service = SubtitleService(SubtitleStream())
    service._config_manager._current = SubtitleConfig(host="0.0.0.0", port=8421)
    assert service.endpoint_url == "http://127.0.0.1:8421/"
    assert service.ws_url == "ws://127.0.0.1:8421/ws/subtitles"
