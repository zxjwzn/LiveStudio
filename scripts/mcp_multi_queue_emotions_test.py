"""LiveStudio MCP 实机脚本: 多队列 + 全情绪 speak/play_emotion 编排

对齐当前 MCP 契约:
  - 表演唯一入口: add_event* → enqueue_draft; 打断 remove_job
  - 长句拆多次 speak, 后句绑前句 end; 语气词不单独成句
  - 每句 speak 并行配一个 play_emotion, end 绑该句 speak.end
  - speak.text 可含 Fish 语调/音效标签; subtitle 用净文本

用法(仓库根目录, LiveStudio 已启动且 MCP 在 9999):

  .venv\\Scripts\\python.exe scripts\\mcp_multi_queue_emotions_test.py

环境变量:
  MCP_URL   默认 http://127.0.0.1:9999/mcp/
  PLATFORM  默认 vtubestudio
  EMOTIONS  逗号分隔子集, 默认测服务端 list_emotions ∩ 本地台词表

约束:
  - 不 stop_idle_animations / disconnect(保留 mouth_sync)
  - 仅在有 idle 未跑时 start_idle_animations
  - 结束后打印 scorecard; 退出码 0=全过
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE = os.environ.get("MCP_URL", "http://127.0.0.1:9999/mcp/").rstrip("/") + "/"
PLATFORM = os.environ.get("PLATFORM", "vtubestudio")

# emotion -> (fish 标签可选, 台词净文本)。标签写入 speak.text; subtitle 用净文本。
# 台词按中文标点拆句后逐句 speak+emotion。
EMOTION_SCRIPTS: dict[str, tuple[str | None, str]] = {
    "joy": ("excited", "诶嘿嘿～你来啦！今天也要元气满满的哦，我会一直陪着你的～"),
    "sadness": ("sad", "呜……对不起，是我不好。下次我会更小心的……"),
    "anger": ("angry", "真是的！怎么可以这样嘛！……哼，勉强原谅你一次。"),
    "surprise": ("excited", "欸？！等、等一下，这是怎么回事？吓我一跳啦！"),
    "smug": ("soft", "呵呵，被我猜中了吧？就说嘛，你藏不住的～"),
    "wry": ("breathy", "哈啊……又来了啊。行吧，我认栽。"),
    "shy": ("embarrassed", "呀……别、别一直盯着看啦，人家会不好意思的……"),
}


def parse_sse(text: str) -> Any:
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    return json.loads(text)


def unwrap(result: dict[str, Any]) -> Any:
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    payload = texts[0] if texts else None
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return payload


class McpSession:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._rid = 0

    async def connect(self) -> None:
        self._rid += 1
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
                    "clientInfo": {"name": "mcp-multi-queue-emotions", "version": "2.0"},
                },
            },
        )
        sid = r.headers.get("mcp-session-id")
        if not sid:
            raise RuntimeError(f"initialize 无 session id: {r.status_code} {r.text[:300]}")
        self.headers["mcp-session-id"] = sid
        await self.client.post(
            BASE,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

    async def t(self, name: str, args: dict[str, Any] | None = None, *, show: bool = True) -> Any:
        self._rid += 1
        r = await self.client.post(
            BASE,
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self._rid,
                "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            },
        )
        data = parse_sse(r.text)
        if "error" in data:
            out: Any = {"_rpc_error": data["error"], "_status": r.status_code}
        else:
            out = unwrap(data.get("result", {}))
        if show:
            s = json.dumps(out, ensure_ascii=False)
            print(f"\n=== {name} === {s[:520]}")
        return out

    async def wait_job(
        self,
        job_id: str,
        label: str,
        *,
        poll: float = 0.4,
        max_s: float = 180.0,
    ) -> dict[str, Any] | None:
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
            brief = []
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


def split_sentences(text: str) -> list[str]:
    """按中文/英文句读拆句; 逗号也拆, 但过滤过短碎片(语气词单独成句)。"""

    parts = re.findall(r"[^。！？.!?…;；，,]*[。！？.!?…;；，,]+|[^。！？.!?…;；，,]+$", text)
    sentences = [p.strip() for p in parts if p.strip()]
    # 过短片段并入下一句(或上一句), 避免「呀……」单独 speak
    merged: list[str] = []
    buf = ""
    for s in sentences:
        candidate = (buf + s).strip() if buf else s
        # 去掉省略号/标点后过短 → 暂存
        core = re.sub(r"[。！？.!?…;；，,\s]+", "", candidate)
        if len(core) < 4:
            buf = candidate
            continue
        merged.append(candidate)
        buf = ""
    if buf:
        if merged:
            merged[-1] = merged[-1] + buf
        else:
            merged.append(buf)
    return merged or [text.strip()]


def with_fish_tag(tag: str | None, sentence: str) -> str:
    if not tag:
        return sentence
    return f"[{tag}]{sentence}"


def hold_ok(speak: dict[str, Any], emotion: dict[str, Any], *, ratio: float = 0.7) -> bool:
    if None in (speak.get("t_start"), speak.get("t_end"), emotion.get("t_start"), emotion.get("t_end")):
        return False
    sd = float(speak["t_end"]) - float(speak["t_start"])
    ed = float(emotion["t_end"]) - float(emotion["t_start"])
    if sd <= 0.05:
        return False
    return ed >= sd * ratio and abs(float(emotion["t_end"]) - float(speak["t_end"])) < 1.2


@dataclass
class Score:
    items: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, ok: bool, **extra: Any) -> None:
        self.items[key] = {"ok": ok, **extra}

    @property
    def all_ok(self) -> bool:
        return bool(self.items) and all(bool(v.get("ok")) for v in self.items.values())


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

    by_id = {str(e.get("id")): e for e in events}
    speaks = [e for e in events if e.get("type") == "speak"]
    emotions = [e for e in events if e.get("type") == "play_emotion"]
    if not speaks or len(speaks) != len(emotions):
        return {
            "ok": False,
            "reason": "pair_mismatch",
            "state": job.get("state"),
            "speaks": len(speaks),
            "emotions": len(emotions),
        }

    # 按 id 序号配对 s1/e1, s2/e2...
    pairs: list[dict[str, Any]] = []
    all_hold = True
    for i in range(1, len(speaks) + 1):
        spk = by_id.get(f"s{i}")
        emo = by_id.get(f"e{i}")
        if spk is None or emo is None:
            # 回退 zip 顺序
            spk = speaks[i - 1]
            emo = emotions[i - 1]
        hok = hold_ok(spk, emo)
        all_hold = all_hold and hok
        sd = (
            float(spk["t_end"]) - float(spk["t_start"])
            if spk.get("t_end") is not None and spk.get("t_start") is not None
            else None
        )
        ed = (
            float(emo["t_end"]) - float(emo["t_start"])
            if emo.get("t_end") is not None and emo.get("t_start") is not None
            else None
        )
        pairs.append(
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
        print(f"  pair {spk.get('id')}/{emo.get('id')}: speak={sd} emotion={ed} HOLD_OK={hok}")

    all_completed = job.get("state") == "completed" and all(
        e.get("status") == "completed" for e in events
    )
    return {
        "ok": bool(all_completed and all_hold and pairs),
        "state": job.get("state"),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


async def ensure_controllers(s: McpSession) -> dict[str, bool]:
    ctrls = await s.t("list_controllers")
    if isinstance(ctrls, list) and any(
        not c.get("running") for c in ctrls if isinstance(c, dict)
    ):
        print(">> start_idle_animations (will NOT stop later)")
        await s.t("start_idle_animations")
        ctrls = await s.t("list_controllers")
    running = {
        c["name"]: bool(c.get("running")) for c in (ctrls or []) if isinstance(c, dict)
    }
    print("controllers:", running)
    return running


async def enqueue_speak_emotion(
    s: McpSession,
    *,
    text: str,
    emotion: str,
    fish_tag: str | None = None,
    transition: float = 0.5,
    show_draft: bool = False,
) -> dict[str, Any]:
    """单 Job: 拆句 → 每句 speak(+Fish 标签)+subtitle 净文本 + play_emotion 撑到该句 end。"""

    await s.t("clear_draft", show=False)
    sentences = split_sentences(text)
    prev: str | None = None
    for i, sentence in enumerate(sentences, start=1):
        sid, eid = f"s{i}", f"e{i}"
        speak_text = with_fish_tag(fish_tag, sentence)
        await s.t(
            "add_event",
            {
                "event_type": "speak",
                "params": {"text": speak_text, "subtitle": sentence},
                "event_id": sid,
                "start_anchor": prev or "group",
                "start_phase": "end" if prev else "start",
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
        prev = sid

    if show_draft:
        await s.t("get_draft")
    enq = await s.t("enqueue_draft", {"delay": 0})
    if not isinstance(enq, dict) or not enq.get("ok"):
        return {"ok": False, "enqueue": enq, "sentences": sentences}
    return {**enq, "sentences": sentences}


async def part_multi_queue(s: McpSession, emotions: list[str]) -> dict[str, Any]:
    """连续 enqueue 多个 Job, 验证 FIFO pending → 串行完成。"""

    print("\n" + "=" * 60)
    print("PART 1: multi-queue FIFO")
    print("=" * 60)
    await s.t("remove_job", {"clear_all": True}, show=False)
    await s.t("clear_draft", show=False)

    # 用前 3 个情绪(不足则重复)各入一队
    picks = (emotions * 3)[:3]
    job_ids: list[str] = []
    for i, emotion in enumerate(picks):
        tag, text = EMOTION_SCRIPTS[emotion]
        # 多队列用短句加速
        short = split_sentences(text)[0]
        enq = await enqueue_speak_emotion(
            s,
            text=short,
            emotion=emotion,
            fish_tag=tag,
        )
        if not enq.get("ok"):
            return {"ok": False, "reason": "enqueue_failed", "enqueue": enq, "index": i}
        job_ids.append(str(enq["job_id"]))
        print(f"  enqueued[{i}] emotion={emotion} job={enq['job_id']} state={enq.get('state')} pos={enq.get('position')}")

    # 第二单应 pending(若第一还在跑)
    q = await s.t("list_jobs", {"include_finished": False})
    pending_n = len((q or {}).get("pending") or []) if isinstance(q, dict) else 0
    running = (q or {}).get("running") if isinstance(q, dict) else None
    print(f"  queue snapshot: running={running and running.get('job_id')} pending={pending_n}")

    finals: list[dict[str, Any]] = []
    for jid, emotion in zip(job_ids, picks):
        job = await s.wait_job(jid, f"q:{emotion}")
        finals.append(summarize_job(job, f"queue:{emotion}:{jid}"))

    order_ok = all(f.get("state") == "completed" for f in finals)
    holds_ok = all(f.get("ok") for f in finals)
    # pending 曾出现 或 连续 job 非全部同时 running(第二单 position>0)
    return {
        "ok": order_ok and holds_ok,
        "job_ids": job_ids,
        "pending_seen": pending_n > 0,
        "results": finals,
    }


async def part_all_emotions(s: McpSession, emotions: list[str]) -> dict[str, Any]:
    """每个情绪单独 Job, 全台词拆句 + emotion hold until speak end。"""

    print("\n" + "=" * 60)
    print("PART 2: all emotions (hold until speak end)")
    print("=" * 60)
    await s.t("remove_job", {"clear_all": True}, show=False)

    out: dict[str, Any] = {}
    for emotion in emotions:
        tag, text = EMOTION_SCRIPTS[emotion]
        print(f"\n>>> emotion={emotion} tag={tag!r}")
        print(f"    text={text}")
        print(f"    sentences={split_sentences(text)}")
        enq = await enqueue_speak_emotion(
            s,
            text=text,
            emotion=emotion,
            fish_tag=tag,
            show_draft=True,
        )
        if not enq.get("ok"):
            out[emotion] = {"ok": False, "enqueue": enq}
            print("  enqueue failed")
            continue
        job = await s.wait_job(str(enq["job_id"]), emotion)
        detail = summarize_job(job, f"emotion:{emotion}")
        out[emotion] = detail
        ctrls = await s.t("list_controllers", show=False)
        ms = next(
            (
                c
                for c in (ctrls or [])
                if isinstance(c, dict) and c.get("name") == "mouth_sync"
            ),
            None,
        )
        print(f"  mouth_sync running: {bool(ms and ms.get('running'))}")
    return out


async def main() -> int:
    print(f"MCP_URL={BASE}")
    print(f"(PLATFORM env ignored; no switch_platform) PLATFORM={PLATFORM}")
    score = Score()

    async with httpx.AsyncClient(timeout=300.0) as client:
        s = McpSession(client)
        try:
            await s.connect()
        except Exception as exc:
            print(f"无法连接 MCP: {exc}")
            print("请先启动 LiveStudio, 并确认 MCP 端口(默认 9999)。")
            return 2

        print("\n" + "=" * 60)
        print("SETUP")
        print("=" * 60)
        await s.t("connect")
        await s.t("get_current_model")
        emotions_raw = await s.t("list_emotions")
        if not isinstance(emotions_raw, list) or not emotions_raw:
            print("list_emotions 为空")
            return 1
        server_emotions = [str(x) for x in emotions_raw]
        print("server emotions:", server_emotions)

        env_filter = os.environ.get("EMOTIONS", "").strip()
        if env_filter:
            want = {x.strip() for x in env_filter.split(",") if x.strip()}
            to_test = [e for e in server_emotions if e in want and e in EMOTION_SCRIPTS]
        else:
            to_test = [e for e in server_emotions if e in EMOTION_SCRIPTS]
        if not to_test:
            print("无交集情绪可测; 检查 EMOTION_SCRIPTS / list_emotions")
            return 1
        print("will test:", to_test)

        running = await ensure_controllers(s)
        score.set("controllers_started", any(running.values()), controllers=running)
        await s.t("remove_job", {"clear_all": True})
        await s.t("clear_draft")

        mq = await part_multi_queue(s, to_test)
        score.set("multi_queue", bool(mq.get("ok")), **{k: v for k, v in mq.items() if k != "ok"})

        er = await part_all_emotions(s, to_test)
        emotions_ok = bool(er) and all(bool(v.get("ok")) for v in er.values())
        score.set("emotions", emotions_ok, details=er)

        ctrls = await s.t("list_controllers", show=False)
        still = {
            c["name"]: bool(c.get("running"))
            for c in (ctrls or [])
            if isinstance(c, dict)
        }
        score.set(
            "controllers_never_stopped",
            all(still.values()) if still else False,
            controllers=still,
        )
        print("\nPOST controllers:", still)

        print("\n" + "=" * 60)
        print("FINAL SCORECARD")
        print("=" * 60)
        print(json.dumps(score.items, ensure_ascii=False, indent=2, default=str))
        print("ALL_OK", score.all_ok)
        return 0 if score.all_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130) from None
