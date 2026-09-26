"""Shared domain enums. Mirrored in frontend/lib/types.ts — keep them in sync."""

from enum import StrEnum


class IntentType(StrEnum):
    QUESTION_ANSWERING = "QUESTION_ANSWERING"
    WHATS_NEW = "WHATS_NEW"
    RECALL_HISTORY = "RECALL_HISTORY"
    COMPARE = "COMPARE"
    RESOURCE_SEARCH = "RESOURCE_SEARCH"
    SHOW_SOURCE = "SHOW_SOURCE"
    FOLLOW_UP = "FOLLOW_UP"
    UNKNOWN = "UNKNOWN"


class EventType(StrEnum):
    VOICE_QUERY = "VOICE_QUERY"
    TEXT_QUERY = "TEXT_QUERY"
    RESOURCE_VIEW = "RESOURCE_VIEW"
    SOURCE_OPEN = "SOURCE_OPEN"
    RESPONSE_GENERATED = "RESPONSE_GENERATED"
    FOLLOW_UP = "FOLLOW_UP"
    RESOURCE_SAVED = "RESOURCE_SAVED"
    SESSION_STARTED = "SESSION_STARTED"


# Events that count as the HCP actually reviewing material ("since I last looked at it").
REVIEW_EVENT_TYPES: frozenset[EventType] = frozenset(
    {EventType.RESOURCE_VIEW, EventType.SOURCE_OPEN, EventType.RESOURCE_SAVED}
)


class ResourceType(StrEnum):
    PRESCRIBING_INFORMATION = "PRESCRIBING_INFORMATION"
    CLINICAL_STUDY = "CLINICAL_STUDY"
    ACCESS_GUIDE = "ACCESS_GUIDE"
    EDUCATIONAL_RESOURCE = "EDUCATIONAL_RESOURCE"


class EntityType(StrEnum):
    PRODUCT = "PRODUCT"
    CONDITION = "CONDITION"
    BIOMARKER = "BIOMARKER"
    TOPIC = "TOPIC"
    POPULATION = "POPULATION"
    RESOURCE = "RESOURCE"


class TemporalReference(StrEnum):
    NONE = "none"
    LAST_INTERACTION = "last_interaction"
    RECENT = "recent"
    SPECIFIC_DATE = "specific_date"


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class InputMode(StrEnum):
    VOICE = "voice"
    TEXT = "text"


class ChangeType(StrEnum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"


class Importance(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
