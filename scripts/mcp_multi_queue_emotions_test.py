"""LiveStudio MCP 实机复现脚本：多队列 + 全情绪 play_emotion(撑到 speak 结束)

用法（在仓库根目录、应用已启动且 MCP 监听 9999 时）:

  .venv\\Scripts\\python.exe scripts\\mcp_multi_queue_emotions_test.py

可选环境变量:
  MCP_URL   默认 http://127.0.0.1:9999/mcp/
  PLATFORM  默认 vtubestudio

约束:
  - 不调用 stop_idle_animations / disconnect（保证 mouth_sync 嘴型）
  - 仅在 idle 控制器未跑时 start_idle_animations
  - 每个情绪: 台词按句拆分,每句一个 speak + play_emotion(撑到该句 speak 结束),句间串接不重叠
  - 多队列: 连续 enqueue 多个 Job，验证 pending 串行
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from typing import Any

import httpx

BASE = os.environ.get("MCP_URL", "http://127.0.0.1:9999/mcp/")
PLATFORM = os.environ.get("PLATFORM", "vtubestudio")

# 二次元少女口吻；每种情绪一段台词(可含多句,逐句触发)
EMOTION_LINES: dict[str, str] = {
    "shy": "呀……别、别一直盯着看啦，人家会不好意思的……",
}


def parse_sse(text: str) -> Any:
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    return json.loads(text)


def unwrap(result: dict) -> Any:
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    payload = texts[0] if texts else None
    try:
        return json.loads(payload) if payload is not None else None
    except Exception:
        return payload


async def call(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    rid: int,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> Any:
    r = await client.post(
        BASE,
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        },
    )
    data = parse_sse(r.text)
    if "error" in data:
        return {"_rpc_error": data["error"], "_status": r.status_code}
    return unwrap(data.get("result", {}))


class McpSession:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._rid = 1

    async def connect(self) -> None:
        r = await self.client.post(
            BASE,
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self._rid,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-multi-queue-emotions", "version": "1.0"},
                },
            },
        )
        sid = r.headers.get("mcp-session-id")
        if not sid:
            raise RuntimeError(f"MCP initialize 无 session id: status={r.status_code} body={r.text[:300]}")
        self.headers["mcp-session-id"] = sid
        await self.client.post(
            BASE,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    async def t(self, name: str, args: dict[str, Any] | None = None, *, show: bool = True) -> Any:
        self._rid += 1
        out = await call(self.client, self.headers, self._rid, name, args)
        if show:
            s = json.dumps(out, ensure_ascii=False)
            print(f"\n=== {name} === {s[:560]}")
        return out

    async def wait_job(self, job_id: str, label: str, *, poll: float = 0.4, max_s: float = 180.0) -> dict[str, Any] | None:
        t0 = time.monotonic()
        last: dict[str, Any] | None = None
        while time.monotonic() - t0 < max_s:
            p = await self.t("get_job", {"job_id": job_id}, show=False)
            job = (p or {}).get("job") if isinstance(p, dict) else None
            if not job:
                await asyncio.sleep(poll)
                continue
            last = job
            elapsed = time.monotonic() - t0
            brief: list[str] = []
            for e in job.get("events", []):
                dur = None
                if e.get("t_start") is not None and e.get("t_end") is not None:
                    dur = round(float(e["t_end"]) - float(e["t_start"]), 2)
                brief.append(f"{e.get('id')}:{e.get('status')}:{dur}")
            print(f"  [{label}] +{elapsed:.1f}s {job.get('state')} | {' '.join(brief)}")
            if job.get("state") in {"completed", "failed", "cancelled"}:
                return job
            await asyncio.sleep(poll)
        return last


def hold_ok(speak: dict[str, Any], emotion: dict[str, Any], *, ratio: float = 0.7) -> bool:
    if None in (
        speak.get("t_start"),
        speak.get("t_end"),
        emotion.get("t_start"),
        emotion.get("t_end"),
    ):
        return False
    sd = float(speak["t_end"]) - float(speak["t_start"])
    ed = float(emotion["t_end"]) - float(emotion["t_start"])
    if sd <= 0.05:
        return False
    return ed >= sd * ratio and abs(float(emotion["t_end"]) - float(speak["t_end"])) < 1.0


def summarize_job(job: dict[str, Any] | None, label: str) -> dict[str, Any]:
    print(f"\n--- {label} ---")
    if not job:
        print("NO JOB")
        return {"ok": False, "reason": "no_job"}
    print(f"state={job.get('state')} error={job.get('error')}")
    events = [e for e in job.get("events", []) if isinstance(e, dict)]
    for e in events:
        ts, te = e.get("t_start"), e.get("t_end")
        dur = (float(te) - float(ts)) if ts is not None and te is not None else None
        print(
            f"  {e.get('id')} type={e.get('type')} status={e.get('status')} "
            f"dur={None if dur is None else round(dur, 2)}s err={e.get('error')}"
        )
    speaks = sorted((e for e in events if e.get("type") == "speak"), key=lambda e: str(e.get("id")))
    emotions = sorted((e for e in events if e.get("type") == "play_emotion"), key=lambda e: str(e.get("id")))
    if not speaks or not emotions:
        return {"ok": False, "reason": "missing_events", "state": job.get("state")}
    pairs = list(zip(speaks, emotions))
    pair_details: list[dict[str, Any]] = []
    all_hold = True
    for spk, emo in pairs:
        hok = hold_ok(spk, emo)
        all_hold = all_hold and hok
        sd = float(spk["t_end"]) - float(spk["t_start"]) if spk.get("t_end") and spk.get("t_start") else None
        ed = float(emo["t_end"]) - float(emo["t_start"]) if emo.get("t_end") and emo.get("t_start") else None
        pair_details.append(
            {
                "speak": spk.get("id"),
                "emotion": emo.get("id"),
                "speak_status": spk.get("status"),
                "emotion_status": emo.get("status"),
                "speak_dur": sd,
                "emotion_dur": ed,
                "hold_ok": hok,
            }
        )
        print(f"  pair {spk.get('id')}/{emo.get('id')}: speak_dur={sd} emotion_dur={ed} HOLD_OK={hok}")
    all_completed = job.get("state") == "completed" and all(e.get("status") == "completed" for e in events)
    return {
        "ok": all_completed and all_hold and bool(pair_details),
        "state": job.get("state"),
        "pair_count": len(pair_details),
        "pairs": pair_details,
    }


async def ensure_controllers(s: McpSession) -> dict[str, bool]:
    ctrls = await s.t("list_controllers")
    if isinstance(ctrls, list) and any(not c.get("running") for c in ctrls if isinstance(c, dict)):
        print(">> start_idle_animations (will NOT stop later)")
        await s.t("start_idle_animations")
        ctrls = await s.t("list_controllers")
    running = {c["name"]: bool(c.get("running")) for c in (ctrls or []) if isinstance(c, dict)}
    print("controllers:", running)
    return running


def split_sentences(text: str) -> list[str]:
    # 在原有符号集合中加入中文逗号 ，
    parts = re.findall(r"[^。！？.!?…;；，]*[。！？.!?…;；，]+|[^。！？.!?…;；，]+$", text)
    sentences = [p.strip() for p in parts if p.strip()]
    return sentences or [text.strip()]


async def enqueue_speak_emotion(
    s: McpSession,
    *,
    text: str,
    emotion: str,
    transition: float = 1,
) -> dict[str, Any]:
    """单 Job: 台词按句拆分,每句一个 speak + play_emotion(撑到该句 speak 结束),句间串接不重叠。"""

    await s.t("clear_draft", show=False)
    prev_speak: str | None = None
    for i, sentence in enumerate(split_sentences(text), start=1):
        sid = f"s{i}"
        eid = f"e{i}"
        await s.t(
            "add_event",
            {
                "event_type": "speak",
                "params": {"text": sentence},
                "event_id": sid,
                "start_anchor": prev_speak or "group",
                "start_phase": "end" if prev_speak else "start",
            },
            show=False,
        )
        await s.t(
            "add_event",
            {
                "event_type": "play_emotion",
                "params": {"emotion": emotion, "transition_duration": transition},
                "event_id": eid,
                "start_anchor": sid,
                "start_phase": "start",
                "delay": 0,
                "end_anchor": sid,
                "end_phase": "end",
                "end_delay": 0,
            },
            show=False,
        )
        prev_speak = sid
    enq = await s.t("enqueue_draft", {"delay": 0})
    if not isinstance(enq, dict) or not enq.get("ok"):
        return {"ok": False, "enqueue": enq}
    return enq


async def main() -> int:
    print(f"MCP_URL={BASE}")
    print(f"PLATFORM={PLATFORM}")
    results: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=300.0) as client:
        s = McpSession(client)
        try:
            await s.connect()
        except Exception as exc:
            print(f"无法连接 MCP: {exc}")
            print("请先启动 LiveStudio，并确认 MCP 端口（默认 9999）。")
            return 2

        print("\n" + "=" * 60)
        print("SETUP")
        print("=" * 60)
        await s.t("switch_platform", {"platform": PLATFORM})
        await s.t("connect")
        await s.t("get_current_model")
        emotions = await s.t("list_emotions")
        if not isinstance(emotions, list) or not emotions:
            print("list_emotions 为空，无法测情绪")
            return 1
        print("emotions from server:", emotions)
        await ensure_controllers(s)
        await s.t("remove_job", {"clear_all": True})
        await s.t("clear_draft")

        # ------------------------------------------------------------------
        # PART 1: 每个情绪单独一 Job，play_emotion 撑到 speak 结束
        # 用 list_emotions 与本地台词表的交集，保证服务端认识
        # ------------------------------------------------------------------
        print("\n" + "=" * 60)
        print("PART 2: 全情绪演出（各自 hold until speak end）")
        print("=" * 60)
        server_emotions = [str(x) for x in emotions]
        # 保持 list_emotions 顺序
        to_test = [e for e in server_emotions if e in EMOTION_LINES]

        emotion_results: dict[str, Any] = {}
        for emotion in to_test:
            print(f"\n>>> emotion={emotion}")
            text = EMOTION_LINES[emotion]
            enq = await enqueue_speak_emotion(s, text=text, emotion=emotion)
            if not isinstance(enq, dict) or not enq.get("ok"):
                emotion_results[emotion] = {"ok": False, "enqueue": enq}
                print("  enqueue failed")
                continue
            job = await s.wait_job(str(enq["job_id"]), emotion)
            detail = summarize_job(job, f"emotion:{emotion}")
            emotion_results[emotion] = detail
            # 确认控制器仍在
            ctrls = await s.t("list_controllers", show=False)
            ms = next((c for c in (ctrls or []) if isinstance(c, dict) and c.get("name") == "mouth_sync"), None)
            print(f"  mouth_sync still running: {bool(ms and ms.get('running'))}")

        results["emotions"] = emotion_results
        results["emotions_all_ok"] = all(bool(v.get("ok")) for v in emotion_results.values()) if emotion_results else False

        ctrls = await s.t("list_controllers", show=False)
        controllers_ok = all(c.get("running") for c in (ctrls or []) if isinstance(c, dict))
        results["controllers_never_stopped"] = controllers_ok
        print("\nPOST controllers:", {c["name"]: c["running"] for c in ctrls if isinstance(c, dict)})

        print("\n" + "=" * 60)
        print("FINAL SCORECARD")
        print("=" * 60)
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        all_ok = bool(results.get("multi_queue", {}).get("ok")) and bool(results.get("emotions_all_ok")) and controllers_ok
        print("ALL_OK", all_ok)
        return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130) from None
