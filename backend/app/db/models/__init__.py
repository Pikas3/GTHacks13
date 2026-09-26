"""ORM models. Import everything here so Alembic autogenerate sees all tables.

Models hold structure only — no business logic.
"""

from app.db.models.conversation import ConversationSession, ConversationTurn
from app.db.models.hcp import HCP, HCPInterest, HCPPreference
from app.db.models.interaction import InteractionEvent
from app.db.models.resource import Resource, ResourceChunk

__all__ = [
    "HCP",
    "HCPInterest",
    "HCPPreference",
    "Resource",
    "ResourceChunk",
    "InteractionEvent",
    "ConversationSession",
    "ConversationTurn",
]
