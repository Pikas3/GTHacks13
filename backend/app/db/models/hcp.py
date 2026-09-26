import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class HCP(TimestampMixin, Base):
    """Synthetic healthcare professional profile."""

    __tablename__ = "hcp"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    specialty: Mapped[str] = mapped_column(String(120))
    organization: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(120))

    preferences: Mapped[list["HCPPreference"]] = relationship(
        back_populates="hcp", cascade="all, delete-orphan", lazy="selectin"
    )
    interests: Mapped[list["HCPInterest"]] = relationship(
        back_populates="hcp", cascade="all, delete-orphan", lazy="selectin"
    )


class HCPPreference(TimestampMixin, Base):
    __tablename__ = "hcp_preference"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hcp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hcp.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(500))
    weight: Mapped[float] = mapped_column(default=0.5)

    hcp: Mapped[HCP] = relationship(back_populates="preferences")


class HCPInterest(Base):
    __tablename__ = "hcp_interest"
    __table_args__ = (UniqueConstraint("hcp_id", "entity", name="uq_hcp_interest_hcp_entity"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hcp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hcp.id", ondelete="CASCADE"), index=True)
    entity: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(default=0.0)
    interaction_count: Mapped[int] = mapped_column(default=0)
    last_interaction_at: Mapped[datetime | None] = mapped_column(server_default=func.now())

    hcp: Mapped[HCP] = relationship(back_populates="interests")
