from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HCP, HCPInterest, HCPPreference
from app.schemas.enums import EntityType
from app.schemas.hcp import HCPDetail, HCPInterestRead, HCPPreferenceRead, HCPRead


class SqlHCPRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_hcps(self) -> list[HCPRead]:
        rows = await self.session.scalars(select(HCP).order_by(HCP.name))
        return [HCPRead.model_validate(r) for r in rows]

    async def get_hcp(self, hcp_id: UUID) -> HCPRead | None:
        row = await self.session.get(HCP, hcp_id)
        return HCPRead.model_validate(row) if row else None

    async def get_detail(self, hcp_id: UUID) -> HCPDetail | None:
        row = await self.session.get(HCP, hcp_id)
        if row is None:
            return None
        detail = HCPDetail.model_validate(row)
        detail.interests.sort(key=lambda i: i.score, reverse=True)
        return detail

    async def get_preferences(self, hcp_id: UUID) -> list[HCPPreferenceRead]:
        rows = await self.session.scalars(
            select(HCPPreference).where(HCPPreference.hcp_id == hcp_id).order_by(HCPPreference.weight.desc())
        )
        return [HCPPreferenceRead.model_validate(r) for r in rows]

    async def get_interests(self, hcp_id: UUID) -> list[HCPInterestRead]:
        rows = await self.session.scalars(
            select(HCPInterest).where(HCPInterest.hcp_id == hcp_id).order_by(HCPInterest.score.desc())
        )
        return [HCPInterestRead.model_validate(r) for r in rows]

    async def upsert_interest(
        self, hcp_id: UUID, entity: str, entity_type: EntityType, new_score: float, at: datetime
    ) -> HCPInterestRead:
        stmt = (
            insert(HCPInterest)
            .values(
                hcp_id=hcp_id,
                entity=entity,
                entity_type=entity_type.value,
                score=new_score,
                interaction_count=1,
                last_interaction_at=at,
            )
            .on_conflict_do_update(
                constraint="uq_hcp_interest_hcp_entity",
                set_={
                    "score": new_score,
                    "interaction_count": HCPInterest.interaction_count + 1,
                    "last_interaction_at": at,
                },
            )
            .returning(HCPInterest)
        )
        row = (await self.session.scalars(stmt)).one()
        return HCPInterestRead.model_validate(row)
