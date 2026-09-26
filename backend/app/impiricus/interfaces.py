from typing import Protocol
from uuid import UUID

from app.schemas.ambient import HCPContext
from app.schemas.hcp import HCPInterestRead
from app.schemas.intelligence import Recommendation
from app.schemas.signals import EngagementSignal


class IONService(Protocol):
    """Conceptual integration with existing Impiricus physician intelligence.

    In production this would call Impiricus services; in the prototype `MockIONService`
    implements it on top of our own Tiger Data tables.
    """

    async def get_hcp_context(self, hcp_id: UUID, entity: str | None = None) -> HCPContext: ...
    async def record_signal(self, signal: EngagementSignal) -> EngagementSignal: ...
    async def get_topic_affinities(self, hcp_id: UUID) -> list[HCPInterestRead]: ...
    async def get_recommended_resource(self, hcp_id: UUID, limit: int = 3) -> list[Recommendation]: ...
    async def get_recent_signals(self, hcp_id: UUID, limit: int = 20) -> list[EngagementSignal]: ...
