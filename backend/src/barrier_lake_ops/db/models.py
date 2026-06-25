"""SQLAlchemy models — briefings / chat_sessions / chat_messages。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DatasetSync(Base):
    """各資料集的同步/更新狀態(資料同步頁讀這張)。"""

    __tablename__ = "dataset_sync"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16))  # live | scheduled | static | manual | upload
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # ok | running | error | pending
    row_count: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)


class Village(Base):
    """村里界 + 戶數人口(由排程收集器寫入)。"""

    __tablename__ = "villages"

    village_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    county: Mapped[str | None] = mapped_column(String(32))
    town: Mapped[str | None] = mapped_column(String(32))
    village: Mapped[str | None] = mapped_column(String(64))
    geometry: Mapped[dict | None] = mapped_column(JSONB)
    households: Mapped[int | None] = mapped_column(Integer)
    population: Mapped[int | None] = mapped_column(Integer)
    elderly_65plus: Mapped[int | None] = mapped_column(Integer)
    children_under6: Mapped[int | None] = mapped_column(Integer)


class LakeState(Base):
    """堰塞湖水位(情境快照)— 應變中心可即時編輯,寫 DB + 記錄時間。"""

    __tablename__ = "lake_states"

    lake_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    water_level_m: Mapped[float | None] = mapped_column(Float)
    storage_million_m3: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LakeThreshold(Base):
    """警戒門檻 — 應變中心可即時編輯,寫 DB + 記錄時間。"""

    __tablename__ = "lake_thresholds"

    lake_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    overflow_elevation_m: Mapped[float | None] = mapped_column(Float)
    red_alert_headroom_m: Mapped[float | None] = mapped_column(Float)
    orange_alert_headroom_m: Mapped[float | None] = mapped_column(Float)
    yellow_alert_headroom_m: Mapped[float | None] = mapped_column(Float)
    updated_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Briefing(Base):
    """每份態勢簡報 = 一筆可追溯稽核紀錄(存輸出 + 驅動它的輸入快照)。"""

    __tablename__ = "briefings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lake_id: Mapped[str | None] = mapped_column(String(64), index=True)
    audience: Mapped[str] = mapped_column(String(32))
    status_color: Mapped[str | None] = mapped_column(String(16))
    headline: Mapped[str | None] = mapped_column(Text)
    key_facts: Mapped[list | None] = mapped_column(JSONB)
    recommended_actions: Mapped[list | None] = mapped_column(JSONB)
    natural_language: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    data_sources_used: Mapped[list | None] = mapped_column(JSONB)
    input_context: Mapped[dict | None] = mapped_column(JSONB)  # Tool 0–4 快照
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lake_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        order_by="ChatMessage.created_at",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str | None] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(64))
    tool_args: Mapped[dict | None] = mapped_column(JSONB)
    tool_result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
