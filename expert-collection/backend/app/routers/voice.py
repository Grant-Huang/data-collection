"""Voice-to-text relay (IMPLEMENTATION_PLAN.md section 17.5): browser <-> this backend <->
Qwen3-ASR-Flash-Realtime, so the DashScope API key never reaches the browser.

Same shape as web-demo/server.py's relay, with two deliberate differences:
- The session config is fixed here, not sent by the browser: 16 kHz mono PCM, Chinese,
  server-side VAD (the mode Alibaba documents for continuous speech such as meeting
  recordings -- an expert narrating a whole process for minutes is exactly that; Manual mode
  is documented as "单次会话持续发送的音频时长累加建议不超过 60 秒", too short for it).
- Only whitelisted event types pass in either direction: the browser may only append audio
  and finish the session; the browser only receives transcription / error / lifecycle events.

Protocol references (checked 2026-09-25): wss URL with `?model=`, `Authorization: Bearer` +
`OpenAI-Beta: realtime=v1` headers; client events session.update / input_audio_buffer.append /
session.finish; server events conversation.item.input_audio_transcription.text (text + stash
preview) and ...completed (transcript).

Not verified against the real service in this sandbox (no DashScope key or network) -- only
against a fake upstream that speaks the same event protocol. `QWEN_ASR_WS_BASE` exists so
tests can point the relay at that fake upstream.
"""
from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect as ws_connect

from .. import settings as app_settings

router = APIRouter(prefix="/api/voice", tags=["voice"])

_SHARED_WS_BASE = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
DEFAULT_MODEL = "qwen3-asr-flash-realtime"

SESSION_CONFIG = {
    "input_audio_format": "pcm",
    "sample_rate": 16000,
    "input_audio_transcription": {"language": "zh"},
    # Server defaults per Alibaba's docs (threshold 0.2, silence 800 ms). Kept at 800 rather
    # than the 400 recommended for snappy chat: an expert pausing to think mid-narration
    # shouldn't split one sentence into two segments.
    "turn_detection": {"type": "server_vad", "threshold": 0.2, "silence_duration_ms": 800},
}

_BROWSER_ALLOWED = {"input_audio_buffer.append", "session.finish"}
_UPSTREAM_FORWARDED = {
    "session.created", "session.updated", "session.finished",
    "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped",
    "conversation.item.input_audio_transcription.text",
    "conversation.item.input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.failed",
    "error",
}


def _voice_config() -> dict:
    return app_settings.get_effective_settings().get("voice", {}) or {}


def _upstream_url(voice: dict) -> str:
    base = os.environ.get("QWEN_ASR_WS_BASE")
    if not base:
        workspace = (voice.get("workspace_id") or "").strip()
        # Workspace-specific domain, same as web-demo/server.py::upstream_ws_base.
        base = f"wss://{workspace}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime" if workspace else _SHARED_WS_BASE
    return f"{base}?model={(voice.get('realtime_model') or DEFAULT_MODEL).strip()}"


@router.get("/status")
def voice_status() -> dict:
    """Lets the frontend decide between the Qwen relay and the browser's own recognizer."""
    voice = _voice_config()
    return {"configured": bool(voice.get("api_key")), "model": voice.get("realtime_model") or DEFAULT_MODEL}


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_text(json.dumps({"type": "relay.error", "code": code, "message": message}, ensure_ascii=False))


@router.websocket("/asr")
async def asr_relay(ws: WebSocket) -> None:
    await ws.accept()
    voice = _voice_config()
    api_key = voice.get("api_key")
    if not api_key:
        await _send_error(ws, "not_configured", "语音识别服务未配置（系统管理 → 语音）")
        await ws.close()
        return

    try:
        upstream = await ws_connect(
            _upstream_url(voice),
            additional_headers={"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"},
            open_timeout=10,
            max_size=10 * 1024 * 1024,
        )
    except Exception as e:  # network / auth / DNS -- all reported the same way to the browser
        await _send_error(ws, "upstream_connect_failed", f"连接语音识别服务失败：{e}")
        await ws.close()
        return

    await upstream.send(json.dumps({"type": "session.update", "session": SESSION_CONFIG}))

    async def browser_to_upstream() -> None:
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") in _BROWSER_ALLOWED:
                    await upstream.send(json.dumps(msg))
        except WebSocketDisconnect:
            pass

    async def upstream_to_browser() -> None:
        async for message in upstream:
            try:
                msg = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                continue
            if msg.get("type") in _UPSTREAM_FORWARDED:
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
            if msg.get("type") == "session.finished":
                return

    up = asyncio.create_task(browser_to_upstream())
    down = asyncio.create_task(upstream_to_browser())
    try:
        await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (up, down):
            t.cancel()
        await upstream.close()
        try:
            await ws.close()
        except RuntimeError:
            pass  # already closed by the browser
