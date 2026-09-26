from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.dependencies import get_stt, get_tts
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import SynthesizeRequest, TranscriptionResult
from app.voice.audio_format import resolve_audio_format
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider
from app.voice.speech_store import speech_store
from app.voice.speech_text import normalize_speech_text

router = APIRouter(prefix="/audio", tags=["audio"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MIN_AUDIO_BYTES_LIVE = 256


class SpeechCreateResponse(BaseModel):
    speech_id: str
    provider: str
    media_type: str
    is_placeholder: bool
    expires_in_s: int = 120


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe(
    audio: UploadFile = File(..., description="Browser-recorded audio (webm/ogg/wav/mp4)"),
    mock_text: Annotated[
        str | None,
        Form(
            description="Mock-STT only: override MOCK_STT_TEXT for demo rehearsal without a key",
        ),
    ] = None,
    stt: SpeechToTextProvider = Depends(get_stt),
) -> TranscriptionResult:
    data = await audio.read()
    fmt = resolve_audio_format(audio.content_type, audio.filename)

    if stt.name == "mock":
        # Optional demo override — ignored for real ElevenLabs STT.
        override = mock_text.strip() if mock_text and mock_text.strip() else None
        with timed("stt.total", provider=stt.name, bytes=len(data)):
            return await stt.transcribe(  # type: ignore[call-arg]
                data, fmt.content_type, fmt.filename, override_text=override
            )

    if not data or len(data) < MIN_AUDIO_BYTES_LIVE:
        raise AppError(
            ErrorCode.AUDIO_TRANSCRIPTION_FAILED,
            "Empty or too-short audio — hold the orb and speak, or use the text box",
        )
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Audio upload too large", status_code=413)

    with timed("stt.total", provider=stt.name, bytes=len(data), content_type=fmt.content_type):
        return await stt.transcribe(data, fmt.content_type, fmt.filename)


@router.post(
    "/synthesize",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}},
)
async def synthesize(body: SynthesizeRequest, tts: TextToSpeechProvider = Depends(get_tts)) -> Response:
    """Returns browser-playable audio bytes. `X-TTS-Placeholder: true` means mock/silent audio."""
    spoken = normalize_speech_text(body.text)
    with timed("tts.total", provider=tts.name, chars=len(spoken)):
        result = await tts.synthesize(spoken)
    return Response(
        content=result.audio,
        media_type=result.media_type,
        headers={
            "X-TTS-Provider": result.provider,
            "X-TTS-Placeholder": str(result.is_placeholder).lower(),
            "Cache-Control": "no-store",
        },
    )


@router.post("/speech", response_model=SpeechCreateResponse, status_code=201)
async def create_speech(body: SynthesizeRequest, tts: TextToSpeechProvider = Depends(get_tts)) -> SpeechCreateResponse:
    """Start synthesis and return a short-lived id. Stream via GET /audio/speech/{id}.

    Preferred for lower time-to-first-audio: the client can open the GET stream as soon
    as the id is returned. Text is never placed in a URL query string.
    """
    speech_id, entry = await speech_store.create(body.text, tts)
    return SpeechCreateResponse(
        speech_id=speech_id,
        provider=entry.provider,
        media_type=entry.media_type,
        is_placeholder=entry.is_placeholder,
    )


@router.get(
    "/speech/{speech_id}",
    response_class=StreamingResponse,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}},
)
async def stream_speech(speech_id: str) -> StreamingResponse:
    entry = await speech_store.get(speech_id)

    async def byte_iter():
        async for chunk in speech_store.stream(speech_id):
            yield chunk

    return StreamingResponse(
        byte_iter(),
        media_type=entry.media_type,
        headers={
            "X-TTS-Provider": entry.provider,
            "X-TTS-Placeholder": str(entry.is_placeholder).lower(),
            "Cache-Control": "no-store",
        },
    )
