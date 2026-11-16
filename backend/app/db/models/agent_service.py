from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class AgentServiceProvider(Base):
    """A custom MCP connection the owner marked as a mailbox or phone-number provider.

    The connection keeps the endpoint, sign-in and tool grants; this row only adds the kind of
    service and the owner's cap on how many resources may exist under it."""

    __tablename__ = "agent_service_provider"

    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("custom_mcp_connection.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), nullable=False)


class AgentServiceResource(Base):
    """One mailbox or phone number the owner holds at a provider. It starts assigned to no agent."""

    __tablename__ = "agent_service_resource"
    __table_args__ = (
        UniqueConstraint("connection_id", "kind", "address", name="uq_agent_service_resource_address"),
        Index("ix_agent_service_resource_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("custom_mcp_connection.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    address: Mapped[str] = mapped_column(String(200), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # The provider's own id for the mailbox or number, when it has one. Display and later calls only.
    provider_resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), nullable=False)


class AgentServiceAssignment(Base):
    """Which agents may be given this resource. No row means no access."""

    __tablename__ = "agent_service_assignment"
    __table_args__ = (Index("ix_agent_service_assignment_resource", "resource_id"),)

    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_service_resource.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), nullable=False)
