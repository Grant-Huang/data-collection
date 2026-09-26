"""Voice input endpoints -- backs icon ①'s "整理后填入输入框" behavior (see
app/speech_polish.py). Icon ②'s "识别后直接发送" and icon ③'s realtime dialog both drive the
existing POST /api/expert-workflows/{id}/turns directly from the browser's own ASR/TTS (see
frontend/src/voice/ -- no server-side speech transport needed for those, see that module's
top comment for why).
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import speech_polish
from ..models import SpeechPolishRequest, SpeechPolishResponse

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/polish", response_model=SpeechPolishResponse)
def polish(req: SpeechPolishRequest) -> SpeechPolishResponse:
    text, polished = speech_polish.polish_transcript(req.text)
    return SpeechPolishResponse(text=text, polished=polished)
