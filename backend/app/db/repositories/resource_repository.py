from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.db.models import Resource, ResourceChunk
from app.schemas.resource import ChunkHit, ResourceChunkRead, ResourceDetail, ResourceRead


def to_resource_read(row: Resource) -> ResourceRead:
    return ResourceRead.model_validate(
        {**{c: getattr(row, c) for c in ResourceRead.model_fields if c != "metadata"}, "metadata": row.metadata_}
    )


class SqlResourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_resources(self, product: str | None = None) -> list[ResourceRead]:
        stmt = select(Resource).order_by(Resource.product, Resource.published_at.desc())
        if product:
            stmt = stmt.where(Resource.product.ilike(product))
        return [to_resource_read(r) for r in await self.session.scalars(stmt)]

    async def get_resource(self, resource_id: UUID) -> ResourceRead | None:
        row = await self.session.get(Resource, resource_id)
        return to_resource_read(row) if row else None

    async def get_detail(self, resource_id: UUID) -> ResourceDetail | None:
        row = await self.session.scalar(
            select(Resource).where(Resource.id == resource_id).options(selectinload(Resource.chunks))
        )
        if row is None:
            return None
        base = to_resource_read(row)
        return ResourceDetail(**base.model_dump(), chunks=[ResourceChunkRead.model_validate(c) for c in row.chunks])

    async def get_many(self, resource_ids: list[UUID]) -> list[ResourceRead]:
        if not resource_ids:
            return []
        rows = await self.session.scalars(select(Resource).where(Resource.id.in_(resource_ids)))
        return [to_resource_read(r) for r in rows]

    async def published_after(self, product: str, after: datetime | None) -> list[ResourceRead]:
        stmt = (
            select(Resource)
            .where(Resource.product.ilike(product), Resource.is_approved.is_(True))
            .order_by(Resource.published_at.desc())
        )
        if after is not None:
            stmt = stmt.where(Resource.published_at > after)
        return [to_resource_read(r) for r in await self.session.scalars(stmt)]

    async def get_superseded(self, resource_id: UUID) -> ResourceRead | None:
        current = await self.session.get(Resource, resource_id)
        if current is None or current.supersedes_resource_id is None:
            return None
        return await self.get_resource(current.supersedes_resource_id)

    async def vector_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        product: str | None = None,
        published_after: datetime | None = None,
        approved_only: bool = True,
        exclude_superseded: bool = True,
    ) -> list[ChunkHit]:
        """pgvector cosine similarity search (HNSW index on resource_chunk.embedding).

        By default only current versions are searched: a resource that a newer resource
        supersedes is excluded (pass exclude_superseded=False for version comparisons).
        """
        distance = ResourceChunk.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(ResourceChunk, Resource, distance)
            .join(Resource, Resource.id == ResourceChunk.resource_id)
            .where(ResourceChunk.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        if approved_only:
            stmt = stmt.where(Resource.is_approved.is_(True))
        if product:
            stmt = stmt.where(Resource.product.ilike(product))
        if published_after is not None:
            stmt = stmt.where(Resource.published_at > published_after)
        if exclude_superseded:
            newer = aliased(Resource)
            stmt = stmt.where(~select(newer.id).where(newer.supersedes_resource_id == Resource.id).exists())
        rows = (await self.session.execute(stmt)).all()
        return [
            ChunkHit(
                chunk=ResourceChunkRead.model_validate(chunk),
                resource=to_resource_read(resource),
                similarity=1.0 - float(dist),
            )
            for chunk, resource, dist in rows
        ]
