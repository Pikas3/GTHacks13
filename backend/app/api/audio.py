from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.dependencies import get_stt, get_tts
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import SynthesizeRequest, TranscriptionResult
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider

router = APIRouter(prefix="/audio", tags=["audio"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe(
    audio: UploadFile = File(..., description="Browser-recorded audio (webm/ogg/wav/mp4)"),
    stt: SpeechToTextProvider = Depends(get_stt),
) -> TranscriptionResult:
    data = await audio.read()
    if not data and stt.name != "mock":
        raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Audio upload too large", status_code=413)
    with timed("stt.total", provider=stt.name):
        return await stt.transcribe(
            data, audio.content_type or "application/octet-stream", audio.filename or "audio.webm"
        )


@router.post(
    "/synthesize",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}},
)
async def synthesize(body: SynthesizeRequest, tts: TextToSpeechProvider = Depends(get_tts)) -> Response:
    """Returns browser-playable audio bytes. `X-TTS-Placeholder: true` means mock/silent audio."""
    with timed("tts.total", provider=tts.name):
        result = await tts.synthesize(body.text)
    return Response(
        content=result.audio,
        media_type=result.media_type,
        headers={
            "X-TTS-Provider": result.provider,
            "X-TTS-Placeholder": str(result.is_placeholder).lower(),
            "Cache-Control": "no-store",
        },
    )
