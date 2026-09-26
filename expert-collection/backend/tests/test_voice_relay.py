"""Voice-to-text relay (IMPLEMENTATION_PLAN.md section 17.5) against a fake upstream that
speaks the Qwen-ASR-Realtime event protocol -- the real service isn't reachable from tests."""
import asyncio
import json
import threading

import pytest
from websockets.asyncio.server import serve

from app import settings as app_settings


class FakeAsrUpstream:
    """Records what the relay sent and answers like the real service would: a partial
    result after the first audio chunk, a final transcript after the second, and
    session.finished on session.finish."""

    def __init__(self):
        self.received: list[dict] = []
        self.headers: dict = {}
        self.port = None
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(5)

    def _run(self):
        asyncio.set_event_loop(self._loop)

        async def handler(conn):
            self.headers = dict(conn.request.headers)
            appends = 0
            async for raw in conn:
                msg = json.loads(raw)
                self.received.append(msg)
                if msg["type"] == "input_audio_buffer.append":
                    appends += 1
                    if appends == 1:
                        await conn.send(json.dumps({"type": "conversation.item.input_audio_transcription.text",
                                                    "text": "设备", "stash": "报警"}))
                    elif appends == 2:
                        await conn.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed",
                                                    "transcript": "设备报警后先停机。"}))
                        await conn.send(json.dumps({"type": "internal.debug", "x": 1}))  # must not be forwarded
                elif msg["type"] == "session.finish":
                    await conn.send(json.dumps({"type": "session.finished"}))
                    return

        async def main():
            async with serve(handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                self._ready.set()
                await asyncio.Future()

        self._loop.run_until_complete(main())


@pytest.fixture
def fake_upstream(monkeypatch):
    up = FakeAsrUpstream()
    monkeypatch.setenv("QWEN_ASR_WS_BASE", f"ws://127.0.0.1:{up.port}")
    return up


def test_status_reports_unconfigured(client):
    assert client.get("/api/voice/status").json()["configured"] is False


def test_relay_refuses_without_key(client):
    with client.websocket_connect("/api/voice/asr") as ws:
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "relay.error" and msg["code"] == "not_configured"


def test_relay_forwards_audio_and_transcripts(client, fake_upstream):
    app_settings.save_settings({"voice": {"api_key": "sk-test", "realtime_model": "qwen3-asr-flash-realtime"}})
    assert client.get("/api/voice/status").json()["configured"] is True

    with client.websocket_connect("/api/voice/asr") as ws:
        # A browser trying to reconfigure the session is ignored (only audio/finish pass).
        ws.send_text(json.dumps({"type": "session.update", "session": {"sample_rate": 8000}}))
        ws.send_text(json.dumps({"type": "input_audio_buffer.append", "audio": "AAAA"}))
        partial = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "input_audio_buffer.append", "audio": "BBBB"}))
        final = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "session.finish"}))
        finished = json.loads(ws.receive_text())

    assert partial == {"type": "conversation.item.input_audio_transcription.text", "text": "设备", "stash": "报警"}
    assert final["transcript"] == "设备报警后先停机。"
    assert finished["type"] == "session.finished"

    # Server-side session config went first; the browser's own session.update never arrived.
    sent_types = [m["type"] for m in fake_upstream.received]
    assert sent_types == ["session.update", "input_audio_buffer.append", "input_audio_buffer.append", "session.finish"]
    session = fake_upstream.received[0]["session"]
    assert session["sample_rate"] == 16000 and session["turn_detection"]["type"] == "server_vad"
    assert fake_upstream.headers.get("authorization") == "Bearer sk-test"
    assert fake_upstream.headers.get("openai-beta") == "realtime=v1"
