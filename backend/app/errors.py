"""Normalized API errors.

Every error leaving the API has the shape:
    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ErrorCode(StrEnum):
    GEMINI_UNAVAILABLE = "GEMINI_UNAVAILABLE"
    ELEVENLABS_UNAVAILABLE = "ELEVENLABS_UNAVAILABLE"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
    INVALID_HCP = "INVALID_HCP"
    INVALID_SESSION = "INVALID_SESSION"
    INVALID_RESOURCE = "INVALID_RESOURCE"
    AUDIO_TRANSCRIPTION_FAILED = "AUDIO_TRANSCRIPTION_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.GEMINI_UNAVAILABLE: 503,
    ErrorCode.ELEVENLABS_UNAVAILABLE: 503,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.NO_EVIDENCE_FOUND: 404,
    ErrorCode.INVALID_HCP: 404,
    ErrorCode.INVALID_SESSION: 404,
    ErrorCode.INVALID_RESOURCE: 404,
    ErrorCode.AUDIO_TRANSCRIPTION_FAILED: 422,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or _DEFAULT_STATUS[code]
        self.details = details or {}


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = {}
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
